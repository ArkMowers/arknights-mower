"""Explicit instance relay selections; passwords are stored as salted hashes."""

import json
import re
from threading import RLock

from werkzeug.security import generate_password_hash

lock = RLock()
DEFAULTS = {
    "enabled": False,
    "credential": "",
    "username": "",
    "password_hash": "",
}


def settings_path():
    from arknights_mower.utils.path import get_path

    return get_path("@app/relay/settings.json")


def load():
    with lock:
        try:
            value = json.loads(settings_path().read_text("utf-8"))
        except FileNotFoundError:
            return dict(DEFAULTS)
        if not isinstance(value, dict):
            raise ValueError("中转配置文件无效，请检查 relay/settings.json")
        return {key: value.get(key, default) for key, default in DEFAULTS.items()}


def public_settings():
    data = load()
    return {
        "enabled": data["enabled"],
        "username": data["username"],
        "credential_saved": bool(data["credential"]),
        "password_saved": bool(data["password_hash"]),
    }


def save(payload, *, token_ready):
    from arknights_mower.utils.config import atomic_write

    if not isinstance(payload, dict) or set(payload) - {
        "enabled",
        "credential",
        "username",
        "password",
    }:
        raise ValueError("中转配置字段无效")
    with lock:
        data = load()
        for key in ("enabled", "username"):
            if key in payload:
                data[key] = payload[key]
        for key in ("credential", "password"):
            value = payload.get(key, "")
            if not isinstance(value, str):
                raise ValueError("凭据或密码格式无效")
            if value:
                if key == "credential":
                    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", value):
                        raise ValueError("请填写管理员发放的中转凭据")
                    data[key] = value
                else:
                    data["password_hash"] = generate_password_hash(
                        value, method="scrypt:32768:8:1"
                    )
        if type(data["enabled"]) is not bool:
            raise ValueError("启用状态无效")
        if (
            not isinstance(data["username"], str)
            or len(data["username"]) > 64
            or ":" in data["username"]
        ):
            raise ValueError("登录用户名无效")
        if data["enabled"] and not token_ready:
            raise ValueError("请先配置访问 Token 并重启实例")
        if data["enabled"] and not all(
            data[key] for key in ("credential", "username", "password_hash")
        ):
            raise ValueError("请填写中转凭据、登录用户名和密码")
        atomic_write(settings_path(), lambda f: json.dump(data, f, ensure_ascii=False))
    return public_settings()
