"""森空岛签到日志中的敏感值遮蔽。"""

import re

from arknights_mower.utils import config

_PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


def redact_signing_text(value, *extra_secrets) -> str:
    """保留日志内容，仅遮蔽已知账号、密码、凭据和手机号。"""
    message = str(value)
    secrets = list(extra_secrets)
    accounts = getattr(config.conf, "skland_info", ())
    if isinstance(accounts, (list, tuple)):
        for account in accounts:
            secrets.extend(
                (getattr(account, "account", ""), getattr(account, "password", ""))
            )
    for secret in sorted({str(item) for item in secrets if item}, key=len, reverse=True):
        message = message.replace(secret, "[已隐藏]")
    return _PHONE_PATTERN.sub("[已隐藏]", message)
