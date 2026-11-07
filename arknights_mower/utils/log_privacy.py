"""遮蔽诊断文本中的可识别敏感值，保留其余多行记录。"""

import ipaddress
import json
import re
from urllib.parse import quote, quote_plus

REDACTED = "[已隐藏]"
_EMAIL = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@(?:[\w-]+\.)+[\w-]+")
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?(?![\w.])")
_HOST_PORT = re.compile(
    r"(?i)(?<![\w.])(?:localhost|(?:[a-z0-9-]+\.)+"
    r"(?!(?:py|js|ts|vue|exe):)[a-z][a-z0-9-]*):\d{2,5}(?!\d)"
)
_IPV6 = re.compile(
    r"\[[0-9a-fA-F:.%\w-]+\](?::\d{1,5})?"
    r"|(?<![\w:])(?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F:.]*(?:%[\w.-]+)?"
)
_USER_HOME = re.compile(
    r"(?i)(?:[a-z]:[\\/]+(?:Users|Documents and Settings)[\\/]+"
    r"|/(?:home|Users)/)[^\\/\r\n\"'<>]+|/root(?=/)"
)
_SECRET_FIELD = re.compile(
    r"(?im)((?:[\"']|\b)(?:api[_-]?key|ai_key|ai_custom_key|token|password|"
    r"pass_code|secret|authorization|cookie|smtp_pass|skland_info|last_serial|"
    r"serial|device_id|adb)(?:[\"']|\b)\s*[:=]\s*)[^\r\n]+"
)
_BEARER = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+")
_QUERY_SECRET = re.compile(
    r"(?i)([?&#](?:token|key|password|secret|api_key)=)[^&\s\"'<>]+"
)
_API_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")
_LEGACY_IDENTITY = re.compile(
    r"(?m)((?:设备初始化完成|正在使用全局配置空间)\s*[:：]\s*)[^\r\n]+"
)


def _hide_address(match):
    value = match.group(0)
    address = value[1 : value.index("]")] if value.startswith("[") else value
    if "." in address and address.count(":") == 1:
        address = address.rsplit(":", 1)[0]
    try:
        ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return value
    return REDACTED


class LogRedactor:
    """在一次导出期间复用明确提供的敏感值，不猜测任意单词是否为设备串号。"""

    def __init__(self, sensitive_values=()):
        values = set()
        for value in sensitive_values:
            if not isinstance(value, str) or not value:
                continue
            values.update(
                (
                    value,
                    json.dumps(value, ensure_ascii=False)[1:-1],
                    quote(value, safe=""),
                    quote_plus(value),
                )
            )
        patterns = [
            (r"(?<!\w)" if value[0].isalnum() else "")
            + re.escape(value)
            + (r"(?!\w)" if value[-1].isalnum() else "")
            for value in sorted(values, key=len, reverse=True)
        ]
        self._known = re.compile("|".join(patterns)) if patterns else None

    def __call__(self, value):
        text = str(value)
        if self._known is not None:
            text = self._known.sub(lambda _: REDACTED, text)
        text = _LEGACY_IDENTITY.sub(lambda match: match[1] + REDACTED, text)
        text = _QUERY_SECRET.sub(lambda match: match[1] + REDACTED, text)
        # 与 AI 证据读取保持同一原则：有凭据字段的行不猜测嵌套值在哪里结束。
        text = _SECRET_FIELD.sub(lambda match: match[1] + REDACTED, text)
        text = _BEARER.sub(lambda match: match[1] + " " + REDACTED, text)
        text = _API_KEY.sub(REDACTED, text)
        text = _EMAIL.sub(REDACTED, text)
        text = _HOST_PORT.sub(REDACTED, text)
        text = _USER_HOME.sub(REDACTED, text)
        text = _IPV6.sub(_hide_address, text)
        return _IPV4.sub(_hide_address, text)


def diagnostic_log_redactor():
    """仅捕获已载入配置中的明确值，不读取密钥文件或完整配置导出。"""
    from arknights_mower.utils import config, path

    conf = config.conf
    values = [path.global_space]
    for name in (
        "account",
        "pass_code",
        "adb",
        "ai_key",
        "ai_custom_key",
        "maa_mirrorchyan_token",
    ):
        values.append(getattr(conf, name, None))
    values.append(getattr(getattr(conf, "webview", None), "token", None))
    for name in (
        "last_serial",
        "adb_path",
        "install_dir",
        "manager_path",
        "config_path",
    ):
        values.append(getattr(getattr(conf, "device", None), name, None))
    values.extend(getattr(conf, "recipient", ()) or ())
    for account in getattr(conf, "skland_info", ()) or ():
        values.extend(
            (getattr(account, "account", None), getattr(account, "password", None))
        )
    return LogRedactor(values)
