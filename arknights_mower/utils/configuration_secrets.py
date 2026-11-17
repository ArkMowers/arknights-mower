import json
import os
from pathlib import Path

from arknights_mower import __rootdir__
from arknights_mower.utils.credential_store import read_credentials, write_credentials
from arknights_mower.utils.path import get_path

_FIELDS = {
    "account": "MOWER_MAIL_ACCOUNT",
    "pass_code": "MOWER_MAIL_PASSWORD",
    "recipient": "MOWER_MAIL_RECIPIENTS",
    "maa_mirrorchyan_token": "MOWER_MAA_MIRRORCHYAN_TOKEN",
    "maa_penguin_id": "MOWER_MAA_PENGUIN_ID",
    "maa_yituliu_id": "MOWER_MAA_YITULIU_ID",
    "ai_key": "MOWER_AI_KEY",
    "ai_custom_key": "MOWER_AI_CUSTOM_KEY",
    "ai_base_url": "MOWER_AI_BASE_URL",
    "skland_info": "MOWER_SKLAND_ACCOUNTS",
}
_WEBVIEW_TOKEN = "MOWER_WEBVIEW_TOKEN"
_LIST_FIELDS = {"recipient", "skland_info"}
_FALLBACK_AI_KEY = "MOWER_AI_FALLBACK_KEY"


def conf_secrets_path(conf_path):
    directory = conf_path.parent
    if directory.name == "config":
        directory = directory.parent
    return directory / "mower.secrets.json"


def legacy_conf_secrets_path(conf_path):
    return conf_secrets_path(conf_path).with_name("legacy-mower.secrets.json")


def read_conf_credentials(conf_path, *, legacy=False):
    return read_credentials(
        legacy_conf_secrets_path(conf_path) if legacy else conf_secrets_path(conf_path),
    )


def split_conf(data):
    clean = dict(data)
    values = {
        variable: clean.pop(field)
        for field, variable in _FIELDS.items()
        if field in clean
    }
    webview = clean.get("webview")
    if isinstance(webview, dict) and "token" in webview:
        webview = dict(webview)
        values[_WEBVIEW_TOKEN] = webview.pop("token")
        clean["webview"] = webview
    return clean, values


def with_conf_secrets(data, values):
    merged = {
        **data,
        **{
            field: values[variable]
            for field, variable in _FIELDS.items()
            if variable in values
        },
    }
    if _WEBVIEW_TOKEN in values and isinstance(merged.get("webview", {}), dict):
        merged["webview"] = {
            **merged.get("webview", {}),
            "token": values[_WEBVIEW_TOKEN],
        }
    return merged


def launch_secrets(explicit):
    if os.environ.get("MOWER_MANAGED") == "1":
        return {}
    values = {}
    for field, variable in (*_FIELDS.items(), ("webview", _WEBVIEW_TOKEN)):
        if variable in explicit or variable not in os.environ:
            continue
        value = os.environ[variable]
        if field in _LIST_FIELDS:
            try:
                value = json.loads(value)
            except (ValueError, RecursionError):
                raise ValueError(f"{variable} 需要 JSON 数组") from None
            if not isinstance(value, list):
                raise ValueError(f"{variable} 需要 JSON 数组")
        values[variable] = value
    return values


def migrate_fallback_ai_key():
    path = get_path("@app/ai.secrets.json", space="")
    encrypted = path.exists()
    saved = read_credentials(path)
    legacy = path.with_name("token.txt")
    if not legacy.is_file() and not os.environ.get("MOWER_DATA_DIR"):
        legacy = Path(__rootdir__).parent / "token.txt"
    try:
        key = legacy.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return
    if not encrypted and _FALLBACK_AI_KEY not in saved:
        write_credentials(path, {**saved, _FALLBACK_AI_KEY: key})
    legacy.unlink(missing_ok=True)


def fallback_ai_key():
    path = get_path("@app/ai.secrets.json", space="")
    saved = read_credentials(path)
    if _FALLBACK_AI_KEY in saved:
        value = saved[_FALLBACK_AI_KEY]
        if not isinstance(value, str):
            raise ValueError("MOWER_AI_FALLBACK_KEY 必须是文本")
        return value
    if path.is_file():
        return os.getenv(_FALLBACK_AI_KEY, "")
    candidates = [path.with_name("token.txt")]
    if not os.environ.get("MOWER_DATA_DIR"):
        candidates.append(Path(__rootdir__).parent / "token.txt")
    for legacy in candidates:
        try:
            return legacy.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            continue
    return os.getenv(_FALLBACK_AI_KEY, "")
