"""Local-only read-only headhunting API. No game account password or gacha writes."""
from __future__ import annotations

import ipaddress
from threading import Lock
from urllib.parse import urlparse

from flask import Blueprint, abort, current_app, jsonify, request

from arknights_mower.utils.gacha_provider import (
    GachaProvider,
    GachaRemoteError,
    GachaSessions,
)
from arknights_mower.utils.gacha_records import GachaArchive, identity

gacha_bp = Blueprint("gacha", __name__, url_prefix="/gacha")
sessions = GachaSessions()
archive_instance = None
archive_lock = Lock()
sms_lock = Lock()
sms_cooldowns: dict[str, float] = {}


def archive() -> GachaArchive:
    global archive_instance
    if archive_instance is None:
        with archive_lock:
            if archive_instance is None:
                archive_instance = GachaArchive()
    return archive_instance


@gacha_bp.before_request
def local_and_authorized():
    # These routes accept SMS codes and temporary account capabilities. Keep
    # them local even if the user's other Mower endpoints are publicly exposed.
    try:
        if not ipaddress.ip_address(request.remote_addr or "").is_loopback:
            abort(403)
    except ValueError:
        abort(403)
    if hasattr(current_app, "token") and request.headers.get("token", "") != current_app.token:
        abort(403)
    if request.method != "GET":
        if request.headers.get("X-Mower-Gacha") != "1":
            abort(403)
        origin = request.headers.get("Origin")
        if origin and urlparse(origin).netloc != request.host:
            abort(403)


@gacha_bp.after_request
def never_cache(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@gacha_bp.errorhandler(ValueError)
@gacha_bp.errorhandler(GachaRemoteError)
def safe_error(error):
    return {"ok": False, "message": str(error)}, 400


def body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("请提供有效的 JSON 请求")
    return data


@gacha_bp.get("/accounts")
def accounts():
    return {"ok": True, "accounts": archive().accounts(), "sessions": sessions.list_public()}


@gacha_bp.post("/send-code")
def send_code():
    import math
    import time

    data = body()
    phone = str(data.get("phone") or "").strip()
    from arknights_mower.utils.gacha_provider import PHONE
    if not PHONE.fullmatch(phone):
        raise ValueError("手机号格式不正确")
    # Restrict repeated requests in the backend, not only in the browser.
    with sms_lock:
        remaining = math.ceil(sms_cooldowns.get(phone, 0) - time.monotonic())
        if remaining > 0:
            return {
                "ok": False,
                "message": f"请在 {remaining} 秒后重新发送验证码",
                "retry_after_seconds": remaining,
            }, 429, {"Retry-After": str(remaining)}
        sms_cooldowns[phone] = time.monotonic() + 90
    provider = GachaProvider()
    try:
        provider.send_code(phone)
    finally:
        provider.close()
    return {"ok": True, "message": "验证码已发送", "retry_after_seconds": 90}


def _session_response(provider: GachaProvider, phone: str, roles):
    key = sessions.add(provider)
    return {
        "ok": True,
        "session_id": key,
        "account": f"***{phone[-4:]}",
        "roles": [role.public() for role in roles],
    }


@gacha_bp.post("/login")
def login():
    data = body()
    phone = str(data.get("phone") or "").strip()
    code = str(data.get("code") or "").strip()
    provider = GachaProvider()
    try:
        roles = provider.login(phone, code)
        return _session_response(provider, phone, roles)
    except Exception:
        provider.close()
        raise


@gacha_bp.post("/login-password")
def login_password():
    data = body()
    phone = str(data.get("phone") or "").strip()
    password = data.get("password")
    if not isinstance(password, str) or len(password) > 128:
        raise ValueError("密码格式不正确")
    provider = GachaProvider()
    try:
        roles = provider.login_password(phone, password)
        return _session_response(provider, phone, roles)
    except Exception:
        provider.close()
        raise


@gacha_bp.post("/select-role")
def select_role():
    data = body()
    key = str(data.get("session_id") or "")
    provider = sessions.get(key)
    role = provider.select_role(str(data.get("uid") or ""), str(data.get("channel") or ""))
    account_id = archive().ensure_account(role.uid, role.channel, role.nickname)
    return {"ok": True, "account_id": account_id, "role": role.public()}


@gacha_bp.post("/sync")
def sync():
    data = body()
    provider = sessions.get(str(data.get("session_id") or ""))
    account_id = str(data.get("account_id") or "")
    role = provider.current_role
    if role is None or identity(role.uid, role.channel) != account_id:
        raise ValueError("当前登录会话没有授权该角色，请重新选择角色")
    return {"ok": True, **provider.fetch_all(archive())}


@gacha_bp.get("/catalog")
def operator_catalog():
    """Public game metadata only. No account credentials or network calls."""
    import json
    from pathlib import Path
    directory = Path(__file__).resolve().parents[1] / "data"
    skill_data = json.loads((directory / "skill_data.json").read_text(encoding="utf-8"))
    base = {}
    for char_id, info in skill_data.get("characters", {}).items():
        if char_id.startswith("char_") and isinstance(info, dict) and info.get("name"):
            base[char_id] = {
                "name": info["name"],
                "rarity": info.get("rarity", 0),
                "profession": info.get("profession") or "",
            }
    extra = json.loads((directory / "gacha_catalog.json").read_text(encoding="utf-8"))
    base.update(extra)
    return {"ok": True, "operators": base}


@gacha_bp.get("/roster")
def roster():
    # Only the existing local Skland cache: do not call login, refresh or scheduler.
    from arknights_mower.utils.gacha_roster import roster_preview
    return {"ok":True,**roster_preview()}


@gacha_bp.post("/refresh-roster")
def refresh_roster():
    """User-triggered Skland refresh through Mower's already registered route."""
    from arknights_mower.utils.gacha_roster import roster_preview

    fetch = current_app.view_functions.get("cultivate_fetch")
    if not callable(fetch):
        raise ValueError("当前 Mower 未启用森空岛同步入口")
    result = fetch()
    if not isinstance(result, dict) or result.get("success") is not True:
        raise ValueError(
            (result.get("message") if isinstance(result, dict) else "")
            or "森空岛手动同步失败，请检查 Mower 的森空岛账号绑定"
        )
    return {
        "ok": True,
        "message": "已刷新本机森空岛干员缓存",
        **roster_preview(),
    }


@gacha_bp.get("/summary")
def summary():
    account_id = str(request.args.get("account_id") or "")
    if not account_id:
        raise ValueError("请先选择角色")
    return {"ok": True, **archive().summary(account_id)}


@gacha_bp.get("/records")
def records():
    account_id = str(request.args.get("account_id") or "")
    if not account_id:
        raise ValueError("请先选择角色")
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
        rarity_text = str(request.args.get("rarity") or "")
        rarity = int(rarity_text) if rarity_text else None
        rarity_min_text = str(request.args.get("rarity_min") or "")
        rarity_min = int(rarity_min_text) if rarity_min_text else None
        start_text = str(request.args.get("start_ms") or "")
        start_ms = int(start_text) if start_text else None
        end_text = str(request.args.get("end_ms") or "")
        end_ms = int(end_text) if end_text else None
    except ValueError as error:
        raise ValueError("筛选或分页参数无效") from error
    return {
        "ok": True,
        "records": archive().list_records(
            account_id,
            limit=limit,
            offset=offset,
            category=str(request.args.get("category") or ""),
            pool_id=str(request.args.get("pool_id") or ""),
            rarity=rarity,
            rarity_min=rarity_min,
            new_only=request.args.get("new_only")=="1",
            search=str(request.args.get("search") or ""),
            start_ms=start_ms,
            end_ms=end_ms,
        ),
    }


@gacha_bp.get("/export")
def export():
    account_id = str(request.args.get("account_id") or "")
    if not account_id:
        raise ValueError("请先选择角色")
    data = archive().export(account_id)
    response = jsonify(data)
    # Safe known UID only; avoid arbitrary user-controlled attachment names.
    response.headers["Content-Disposition"] = "attachment; filename=mower-gacha-backup.json"
    return response


@gacha_bp.post("/logout")
def logout():
    sessions.remove(str(body().get("session_id") or ""))
    return {"ok": True}
