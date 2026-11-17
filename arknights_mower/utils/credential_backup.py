"""Password-protected business credentials, independent of configuration ZIPs."""

import base64
import json
import os
import stat
import threading
from contextlib import contextmanager
from uuid import uuid4

from cryptography.exceptions import InvalidTag, UnsupportedAlgorithm
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from arknights_mower.utils import credential_store
from arknights_mower.utils.configuration_secrets import _FIELDS, conf_secrets_path
from arknights_mower.utils.github_download import normalize_token, token_secrets_path
from arknights_mower.utils.path import get_path

MAX_BACKUP_BYTES = 4 * 1024 * 1024
_MAX_PLAINTEXT_BYTES = 2 * 1024 * 1024
_FORMAT = "mower-credential-backup"
_KDF = "scrypt-131072-8-1"
_AAD = b"Arknights Mower credential backup v1 / scrypt-131072-8-1 / AES-256-GCM"
_KDF_LOCK = threading.Lock()
_GROUP_LABELS = {
    "main": "当前实例业务凭据",
    "yituliu": "当前实例一图流 Token",
    "network": "共享 GitHub Token",
    "ai": "共享 AI 备用密钥",
}
_GROUP_FIELDS = {
    "main": frozenset(_FIELDS.values()),
    "yituliu": frozenset({"MOWER_YITULIU_TOKEN"}),
    "network": frozenset({"MOWER_GITHUB_TOKEN"}),
    "ai": frozenset({"MOWER_AI_FALLBACK_KEY"}),
}
_SKLAND_BOOLEANS = {
    "cultivate_select",
    "arknights_isCheck",
    "endfield_isCheck",
    "sign_in_official",
    "sign_in_bilibili",
    "sign_in_endfield_official",
    "sign_in_endfield_bilibili",
}


class CredentialBackupError(ValueError):
    """A credential backup cannot be validated or safely applied."""


class CredentialBackupRecoveryError(CredentialBackupError):
    """A failed restore could not restore every original file."""


def _password_bytes(password):
    try:
        if not isinstance(password, str) or len(password) < 12:
            raise ValueError
        encoded = password.encode("utf-8")
        if len(encoded) > 1024:
            raise ValueError
        return encoded
    except (ValueError, UnicodeError):
        raise CredentialBackupError(
            "备份口令至少需要 12 个字符，UTF-8 编码不能超过 1024 字节"
        ) from None


def _derive(password, salt):
    if not _KDF_LOCK.acquire(timeout=10):
        raise CredentialBackupError("凭据备份正在处理，请稍后重试")
    try:
        return Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).derive(password)
    except (UnsupportedAlgorithm, MemoryError):
        raise CredentialBackupError("当前运行环境无法执行凭据备份加密") from None
    finally:
        _KDF_LOCK.release()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")


def _validate_groups(groups):
    if not isinstance(groups, dict) or not groups or set(groups) - _GROUP_FIELDS.keys():
        raise ValueError
    for group, values in groups.items():
        if not isinstance(values, dict) or set(values) - _GROUP_FIELDS[group]:
            raise ValueError
        for field, value in values.items():
            if field == "MOWER_MAIL_RECIPIENTS":
                if not isinstance(value, list) or any(
                    not isinstance(v, str) for v in value
                ):
                    raise ValueError
            elif field == "MOWER_SKLAND_ACCOUNTS":
                if not isinstance(value, list):
                    raise ValueError
                for account in value:
                    if not isinstance(account, dict):
                        raise ValueError
                    if set(account) - (_SKLAND_BOOLEANS | {"account", "password"}):
                        raise ValueError
                    if any(
                        not isinstance(v, str)
                        if k in {"account", "password"}
                        else type(v) is not bool
                        for k, v in account.items()
                    ):
                        raise ValueError
            elif not isinstance(value, str):
                raise ValueError
            if field == "MOWER_GITHUB_TOKEN" and normalize_token(value) != value:
                raise ValueError
            if field == "MOWER_YITULIU_TOKEN" and value:
                from arknights_mower.utils.yituliu_sync import _TOKEN_PATTERN

                if not _TOKEN_PATTERN.fullmatch(value):
                    raise ValueError
    if not any(groups.values()):
        raise ValueError
    return groups


def _manifest(groups):
    rows = [
        {
            "id": group,
            "label": label,
            "count": len(groups[group]),
            "clear_count": sum(
                value == "" or value == [] for value in groups[group].values()
            ),
        }
        for group, label in _GROUP_LABELS.items()
        if groups.get(group)
    ]
    return {
        "version": 1,
        "groups": rows,
        "field_count": sum(row["count"] for row in rows),
        "clear_count": sum(row["clear_count"] for row in rows),
        "preserves_access_token": True,
        "includes_saved_profiles": False,
    }


def _decode(raw, password):
    password = _password_bytes(password)
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BACKUP_BYTES:
        raise CredentialBackupError("凭据备份文件无效或超过 4 MiB")
    try:
        envelope = json.loads(raw, object_pairs_hook=_unique_object)
        if not isinstance(envelope, dict) or set(envelope) != {
            "format",
            "version",
            "kdf",
            "salt",
            "nonce",
            "ciphertext",
        }:
            raise ValueError
        if (
            envelope["format"] != _FORMAT
            or type(envelope["version"]) is not int
            or envelope["version"] != 1
            or envelope["kdf"] != _KDF
        ):
            raise ValueError
        salt, nonce, ciphertext = (
            base64.b64decode(envelope[key], validate=True)
            for key in ("salt", "nonce", "ciphertext")
        )
        if (
            len(salt) != 16
            or len(nonce) != 12
            or not 16 <= len(ciphertext) <= _MAX_PLAINTEXT_BYTES + 16
        ):
            raise ValueError
        plaintext = AESGCM(_derive(password, salt)).decrypt(nonce, ciphertext, _AAD)
        payload = json.loads(plaintext, object_pairs_hook=_unique_object)
        if not isinstance(payload, dict) or set(payload) != {"version", "groups"}:
            raise ValueError
        if type(payload["version"]) is not int or payload["version"] != 1:
            raise ValueError
        return _validate_groups(payload["groups"])
    except CredentialBackupError:
        raise
    except (InvalidTag, ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        raise CredentialBackupError("备份口令错误或凭据备份文件已损坏") from None


@contextmanager
def _locked_targets():
    from arknights_mower.utils import config, network_settings, yituliu_sync
    from arknights_mower.utils.config_backup import backup_lock
    from arknights_mower.utils.workshop_config import workshop_lock

    with (
        backup_lock,
        workshop_lock,
        config._CONF_WRITE_LOCK,
        yituliu_sync._lock,
        network_settings._environment_lock,
        network_settings._settings_file_lock(),
    ):
        yield {
            "main": conf_secrets_path(config.conf_path),
            "yituliu": yituliu_sync.token_secrets_path(),
            "network": token_secrets_path(network_settings.settings_path()),
            "ai": get_path("@app/ai.secrets.json", space=""),
        }


def _read_saved(path):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {}, None
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_BACKUP_BYTES:
        raise CredentialBackupError("本机凭据文件不是普通文件或超过备份大小限制")
    values = credential_store.read_credentials(path)
    original = path.read_bytes()
    if credential_store.decode_credentials(original) != values:
        raise CredentialBackupError("本机凭据已变化，请重新预览后重试")
    return values, original


def export_credential_backup(password):
    """Export saved business fields; access Tokens and profile snapshots stay local."""
    encoded_password = _password_bytes(password)
    with _locked_targets() as targets:
        groups = {}
        for group, path in targets.items():
            saved, _ = _read_saved(path)
            values = {
                key: value
                for key, value in saved.items()
                if key in _GROUP_FIELDS[group]
            }
            if values:
                groups[group] = values
        if not groups:
            raise CredentialBackupError("没有可导出的已保存业务凭据")
        try:
            _validate_groups(groups)
            plaintext = _json_bytes({"version": 1, "groups": groups})
        except (ValueError, TypeError, RecursionError, UnicodeError):
            raise CredentialBackupError("本机业务凭据格式无效，无法导出") from None
    if len(plaintext) > _MAX_PLAINTEXT_BYTES:
        raise CredentialBackupError("业务凭据超过备份大小限制")
    salt, nonce = os.urandom(16), os.urandom(12)
    ciphertext = AESGCM(_derive(encoded_password, salt)).encrypt(nonce, plaintext, _AAD)
    return _json_bytes(
        {
            "format": _FORMAT,
            "version": 1,
            "kdf": _KDF,
            "salt": base64.b64encode(salt).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }
    )


def inspect_credential_backup(raw, password):
    """Return counts and fixed labels without exposing credential values or paths."""
    return _manifest(_decode(raw, password))


def _yituliu_metadata_change():
    from arknights_mower.utils.yituliu_sync import _settings_path

    path = _settings_path()
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    try:
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_BACKUP_BYTES:
            raise ValueError
        original = path.read_bytes()
        saved = json.loads(original, object_pairs_hook=_unique_object)
        if not isinstance(saved, dict):
            raise ValueError
        clean = {
            key: value
            for key, value in saved.items()
            if key
            not in {
                "last_synced_at",
                "last_synced_count",
                "last_synced_fingerprint",
                "last_attempt_at",
                "last_sync_error",
            }
        }
        if clean == saved:
            return None
        return path, original, _json_bytes(clean)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise CredentialBackupError("一图流同步记录无法读取，已保留原文件") from None


def _write_metadata_bytes(path, raw):
    from arknights_mower.utils.config import atomic_write

    atomic_write(path, lambda stream: stream.buffer.write(raw))
    path.chmod(0o600)
    if path.read_bytes() != raw:
        raise CredentialBackupError("一图流同步记录保存后校验失败")


def import_credential_backup(raw, password, *, activate=None):
    """Merge authenticated fields and roll back exact bytes if storage or activation fails."""
    groups = _decode(raw, password)
    from arknights_mower.utils import config_backup, config_profiles

    with _locked_targets() as targets:
        originals, changes = {}, {}
        metadata_change = None
        for group, incoming in groups.items():
            if not incoming:
                continue
            path = targets[group]
            saved, original = _read_saved(path)
            merged = {**saved, **incoming}
            if merged != saved:
                originals[path] = original
                changes[path] = merged
                if group == "yituliu":
                    metadata_change = _yituliu_metadata_change()
        if metadata_change is not None:
            path, original, _ = metadata_change
            originals[path] = original
        registry = (
            config_profiles._read_registry() or config_profiles._initial_registry()
        )
        index_path = config_profiles._root() / "index.json"
        originals[index_path] = config_profiles._regular_bytes(
            index_path, config_profiles.MAX_INDEX_BYTES, optional=True
        )
        active_path = config_profiles._profile_path(registry["active_id"])
        initial_archive = None
        if not active_path.exists():
            initial_archive = config_profiles.export_current_archive()
            originals[active_path] = None
        registry["generation"] = uuid4().hex
        attempted = []
        try:
            for path, values in changes.items():
                attempted.append(path)
                credential_store.write_credentials(path, values)
            if metadata_change is not None:
                path, _, raw_metadata = metadata_change
                attempted.append(path)
                _write_metadata_bytes(path, raw_metadata)
            if initial_archive is not None:
                attempted.append(active_path)
                config_backup._write_bytes(active_path, initial_archive)
                if active_path.read_bytes() != initial_archive:
                    raise CredentialBackupError("当前档案保存后校验失败")
            attempted.append(index_path)
            config_profiles._write_registry(registry)
            if config_profiles._read_registry() != registry:
                raise CredentialBackupError("配置版本保存后校验失败")
            if activate is not None:
                activate()
        except BaseException as error:
            failed = False
            for path in reversed(attempted):
                original = originals[path]
                try:
                    if (path.read_bytes() if path.is_file() else None) != original:
                        credential_store.restore_credentials(path, original)
                except BaseException:
                    failed = True
            if failed:
                raise CredentialBackupRecoveryError(
                    "凭据恢复失败且无法完整回滚，请保留原文件并检查文件权限"
                ) from None
            if not isinstance(error, Exception):
                raise
            raise CredentialBackupError("凭据恢复未完成，已恢复原文件") from None
    return {
        **_manifest(groups),
        "updated_groups": len(changes),
        "generation": registry["generation"],
    }
