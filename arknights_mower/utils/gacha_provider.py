"""Original local-only adapter for the Arknights CN user-center endpoints.

These are first-party web endpoints, not a published third-party API contract.
All login credentials remain in this process; only draw history is persisted.
"""
from __future__ import annotations

import re
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

import requests

from arknights_mower.utils.gacha_records import channel_name, normalize_record

PHONE = re.compile(r"^1[3-9][0-9]{9}$")
CODE = re.compile(r"^[0-9]{4,8}$")
AUTH = "https://as.hypergryph.com"
BINDING = "https://binding-api-account-prod.hypergryph.com/account/binding/v1"
GAME = "https://ak.hypergryph.com/user/api"
USER_CENTER_APP = "be36d44aa36bfb5b"
DEFAULT_TIMEOUT = (8, 25)
SESSION_TTL = 12 * 3600


class GachaRemoteError(Exception):
    """Safe user-facing error. Never include bearer tokens or complete responses."""


def _redacted_message(data: dict, fallback: str = "官方接口暂不可用") -> str:
    msg = data.get("message") or data.get("msg")
    msg = str(msg or fallback)
    # Untrusted server errors can occasionally contain keys/URLs: do not echo them.
    return msg[:96] if "token" not in msg.lower() and "cookie" not in msg.lower() else fallback


def _data(response: requests.Response, label: str, allow_empty: bool = False):
    try:
        data = response.json()
    except ValueError as error:
        raise GachaRemoteError(f"{label}未返回有效数据；可能是官网接口调整或网络拦截") from error
    if not isinstance(data, dict):
        raise GachaRemoteError(f"{label}的数据结构异常")
    reason = str(data.get("reason") or "")
    if reason in {"UN_LOGIN", "MissingCookie"}:
        raise GachaRemoteError("官网授权已失效，请重新使用短信验证码登录")
    status = data.get("status", data.get("code", 0))
    if response.status_code != 200 or status != 0:
        raise GachaRemoteError(f"{label}失败：{_redacted_message(data)}")
    if "data" not in data:
        if allow_empty:
            return {}
        raise GachaRemoteError(f"{label}未返回 data 字段")
    return data["data"] or {}


@dataclass
class Role:
    uid: str
    channel: str
    nickname: str
    channel_label: str

    def public(self) -> dict:
        return {
            "uid": self.uid,
            "channel": self.channel,
            "nickname": self.nickname,
            "channel_label": self.channel_label,
        }


class GachaProvider:
    def __init__(self, session: requests.Session | None = None):
        self.http = session or requests.Session()
        self.http.headers.update({"User-Agent": "Mower/4.1.6 GachaReadOnly"})
        self.account_token = ""
        self.oauth_token = ""
        self.roles: list[Role] = []
        self.current_role: Role | None = None
        self.role_token = ""
        self.role_cookie = ""

    def _post(self, url: str, body: dict, label: str, allow_empty: bool = False):
        try:
            response = self.http.post(url, json=body, timeout=DEFAULT_TIMEOUT)
            return _data(response, label, allow_empty=allow_empty), response
        except requests.RequestException as error:
            raise GachaRemoteError(f"{label}网络请求失败，请检查官网连接或 Mower 网络代理") from error

    def _get(self, url: str, params: dict, label: str, headers: dict | None = None):
        try:
            response = self.http.get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
            return _data(response, label)
        except requests.RequestException as error:
            raise GachaRemoteError(f"{label}网络请求失败，请检查官网连接或 Mower 网络代理") from error

    def send_code(self, phone: str):
        if not PHONE.fullmatch(phone or ""):
            raise ValueError("请输入正确的中国大陆手机号")
        self._post(
            f"{AUTH}/general/v1/send_phone_code",
            {"phone": phone, "type": 2},
            "发送短信验证码",
            allow_empty=True,
        )

    def login(self, phone: str, code: str) -> list[Role]:
        """Authenticate by SMS; never store the code in the provider."""
        if not PHONE.fullmatch(phone or "") or not CODE.fullmatch(code or ""):
            raise ValueError("手机号或短信验证码格式不正确")
        token_data, _ = self._post(
            f"{AUTH}/user/auth/v2/token_by_phone_code",
            {"phone": phone, "code": code},
            "短信验证",
        )
        return self._authorize((token_data or {}).get("token"))

    def login_password(self, phone: str, password: str) -> list[Role]:
        """Optional existing Hypergryph phone/password login. No password persistence."""
        if not PHONE.fullmatch(phone or "") or not isinstance(password, str) or not 1 <= len(password) <= 128:
            raise ValueError("请输入正确的手机号和密码")
        token_data, _ = self._post(
            f"{AUTH}/user/auth/v1/token_by_phone_password",
            {"phone": phone, "password": password},
            "密码验证",
        )
        return self._authorize((token_data or {}).get("token"))

    def _authorize(self, token) -> list[Role]:
        self.account_token = str(token or "")
        if not self.account_token:
            raise GachaRemoteError("官方验证未返回授权凭据，请重新登录")
        oauth_data, _ = self._post(
            f"{AUTH}/user/oauth2/v2/grant",
            {"token": self.account_token, "appCode": USER_CENTER_APP, "type": 1},
            "授权用户中心",
        )
        self.oauth_token = str((oauth_data or {}).get("token") or "")
        if not self.oauth_token:
            raise GachaRemoteError("官方授权结构已变化，未获得用户中心 token")
        binding = self._get(
            f"{BINDING}/binding_list",
            {"token": self.oauth_token, "appCode": "arknights"},
            "读取绑定角色",
        )
        apps = binding.get("list", []) if isinstance(binding, dict) else []
        unique = set()
        roles = []
        for app in apps:
            if "arknights" not in str(app.get("appCode", "")).lower():
                continue
            for entry in app.get("bindingList", []):
                uid = str(entry.get("uid") or "").strip()
                if not uid:
                    continue
                label = str(entry.get("channelName") or "")
                channel = channel_name(label, entry.get("isOfficial"))
                if (channel, uid) in unique:
                    continue
                unique.add((channel, uid))
                roles.append(
                    Role(
                        uid=uid,
                        nickname=str(entry.get("nickname") or entry.get("nickName") or uid),
                        channel=channel,
                        channel_label=label or {"official": "官服", "bilibili": "B服"}.get(channel, "其他"),
                    )
                )
        if not roles:
            raise GachaRemoteError(
                "没有读取到已绑定的明日方舟角色。B服如未绑定鹰角通行证，暂不能通过此短信通道读取"
            )
        self.roles = roles
        return roles

    def select_role(self, uid: str, channel: str) -> Role:
        role = next((r for r in self.roles if r.uid == uid and r.channel == channel), None)
        if role is None or not self.oauth_token:
            raise ValueError("请先登录，并从已验证的绑定角色中选择")
        token_data, _ = self._post(
            f"{BINDING}/u8_token_by_uid",
            {"token": self.oauth_token, "uid": role.uid},
            "角色授权",
        )
        token = str((token_data or {}).get("token") or "")
        if not token:
            raise GachaRemoteError("角色授权未返回凭据")
        _, response = self._post(
            f"{GAME}/role/login",
            {"token": token, "source_from": "", "share_type": "", "share_by": ""},
            "登录明日方舟角色",
            allow_empty=True,
        )
        cookie = response.cookies.get("ak-user-center")
        if not cookie:
            raise GachaRemoteError("官方未返回角色会话 Cookie，不能读取寻访记录")
        self.current_role = role
        self.role_token = token
        self.role_cookie = cookie
        return role

    def _gacha_get(self, endpoint: str, params: dict):
        if self.current_role is None or not self.role_token or not self.role_cookie:
            raise GachaRemoteError("请先完成角色授权")
        return self._get(
            f"{GAME}/inquiry/gacha/{endpoint}",
            params,
            "读取寻访记录",
            {
                "x-role-token": self.role_token,
                "x-account-token": self.account_token,
                "Cookie": f"ak-user-center={self.role_cookie}",
                "Referer": "https://ak.hypergryph.com/user/headhunting",
            },
        )

    def fetch_all(self, archive, page_size: int = 50, max_pages: int = 200) -> dict:
        role = self.current_role
        if role is None:
            raise GachaRemoteError("请选择角色")
        account_id = archive.ensure_account(role.uid, role.channel, role.nickname)
        raw_categories = self._gacha_get("cate", {"uid": role.uid})
        categories = raw_categories if isinstance(raw_categories, list) else (
            raw_categories.get("list", []) if isinstance(raw_categories, dict) else []
        )
        if not categories:
            raise GachaRemoteError("官网没有返回可查询的寻访卡池分类")
        added = 0
        fetched = 0
        skipped = 0
        warnings: list[str] = []
        for category in categories:
            category_id = str(category.get("id") or category.get("category") or "")
            if not category_id:
                continue
            cursor = None
            seen = set()
            try:
                for _page in range(max_pages):
                    params: dict[str, Any] = {
                        "uid": role.uid, "category": category_id, "size": page_size
                    }
                    if cursor is not None:
                        params.update({"pos": cursor[0], "gachaTs": cursor[1]})
                    data = self._gacha_get("history", params)
                    if not isinstance(data, dict) or not isinstance(data.get("list"), list):
                        raise GachaRemoteError(f"卡池 {category_id} 的分页格式已变化")
                    page = data["list"]
                    if not page:
                        break
                    normalized = []
                    for row in page:
                        try:
                            normalized.append(normalize_record(row, category_id))
                        except ValueError:
                            skipped += 1
                    fetched += len(page)
                    # Commit each page: network failure never discards earlier pages.
                    added += archive.append(account_id, normalized)
                    last = page[-1]
                    next_cursor = (str(last.get("pos")), str(last.get("gachaTs")))
                    if not data.get("hasMore"):
                        break
                    if next_cursor in seen or cursor == next_cursor or next_cursor[1] == "None":
                        raise GachaRemoteError(f"卡池 {category_id} 分页游标没有推进")
                    seen.add(next_cursor)
                    cursor = next_cursor
                else:
                    warnings.append(f"{category_id} 超过本次最大分页数，已保存已获取部分")
            except GachaRemoteError as error:
                warnings.append(f"{category_id}：{error}")
        if not warnings:
            archive.append(account_id, [], finished=True)
        return {
            "account_id": account_id,
            "added": added,
            "fetched": fetched,
            "skipped": skipped,
            "categories": len(categories),
            "warnings": warnings,
        }

    def close(self):
        self.account_token = ""
        self.oauth_token = ""
        self.role_token = ""
        self.role_cookie = ""
        self.roles = []
        self.current_role = None
        self.http.close()


class GachaSessions:
    """Ephemeral per-login state; no credentials on disk or in frontend JSON."""
    def __init__(self):
        self._lock = threading.RLock()
        self._sessions: dict[str, tuple[float, GachaProvider]] = {}

    def add(self, provider: GachaProvider) -> str:
        key = secrets.token_urlsafe(28)
        with self._lock:
            self._sessions[key] = (time.monotonic(), provider)
        return key

    def get(self, key: str) -> GachaProvider:
        with self._lock:
            item = self._sessions.get(key)
            if item is None:
                raise ValueError("登录已过期，请重新验证")
            created, provider = item
            if time.monotonic() - created > SESSION_TTL:
                del self._sessions[key]
                provider.close()
                raise ValueError("登录会话已过期，请重新验证")
            return provider

    def list_public(self) -> list[dict]:
        output = []
        with self._lock:
            for key, (created, provider) in list(self._sessions.items()):
                if time.monotonic() - created > SESSION_TTL:
                    self._sessions.pop(key, None)
                    provider.close()
                    continue
                output.append({
                    "session_id": key,
                    "roles": [role.public() for role in provider.roles],
                    "selected": provider.current_role.public() if provider.current_role else None,
                })
        return output

    def remove(self, key: str):
        with self._lock:
            item = self._sessions.pop(key, None)
            if item:
                item[1].close()
