"""森空岛签到日志中的敏感值遮蔽。"""

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone

from arknights_mower.utils import config

_PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_SKLAND_TIMEZONE = timezone(timedelta(hours=8))


def skland_day(timestamp: float | None = None) -> date:
    if timestamp is None:
        return datetime.now(_SKLAND_TIMEZONE).date()
    return datetime.fromtimestamp(timestamp, _SKLAND_TIMEZONE).date()


def sign_role_key(account: str, game: str, role_id: str, server_id: str = "") -> str:
    identity = json.dumps(
        [str(account).strip(), str(game).strip(), str(role_id), str(server_id)],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _mask_secret(value: str) -> str:
    if _PHONE_PATTERN.fullmatch(value):
        return f"{value[:3]}****{value[-4:]}"
    if "@" in value:
        local, _, domain = value.partition("@")
        if local and domain:
            return f"{_mask_secret(local)}@{domain}"
    if len(value) <= 3:
        return "*" * len(value)
    visible = 1 if len(value) < 8 else 2
    return value[:visible] + "*" * (len(value) - visible * 2) + value[-visible:]


def mask_account(value: str) -> str:
    """遮蔽账号：手机号保留首尾，邮箱遮蔽本地部分，其他值保留首尾字符。"""
    return _mask_secret(str(value or "").strip())


def redact_signing_text(value, *extra_secrets) -> str:
    """保留日志内容及可辨认的前后字符，遮蔽敏感值中间部分。"""
    message = str(value)
    secrets = list(extra_secrets)
    accounts = getattr(config.conf, "skland_info", ())
    if isinstance(accounts, (list, tuple)):
        for account in accounts:
            secrets.extend(
                (getattr(account, "account", ""), getattr(account, "password", ""))
            )
    for secret in sorted(
        {str(item) for item in secrets if item}, key=len, reverse=True
    ):
        message = message.replace(secret, _mask_secret(secret))
    return _PHONE_PATTERN.sub(lambda match: _mask_secret(match.group(0)), message)
