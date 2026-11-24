"""Mower 客户端支持的专用中转协议 v1 操作。"""

import base64
import json
import re
from urllib.parse import unquote, urlsplit

DOMAIN = "free.mower.work"
PORT = 58000
CONNECT_URL = f"wss://{DOMAIN}:{PORT}/__mower/connect"
VERSION = 1
MAX_BODY = 6 * 1024 * 1024
MAX_FRAME = 9 * 1024 * 1024
MAX_PENDING = 8
MAX_SOCKETS = 4
SUBDOMAIN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?\Z")
# These operations have no facility for choosing a network destination.
SOCKETS = {"/log": "log", "/ws/chat": "ws_chat"}


def valid_subdomain(value):
    return (
        isinstance(value, str)
        and SUBDOMAIN.fullmatch(value) is not None
        and value not in {"www", "admin", "api", "mail", "free"}
    )


def public_origin(subdomain):
    if not valid_subdomain(subdomain):
        raise ValueError("子域名须为 1 至 32 位小写字母、数字或中间的连字符")
    return f"https://{subdomain}.{DOMAIN}:{PORT}"


HTTP_METHODS = {"GET", "HEAD", "POST", "PATCH", "PUT", "DELETE"}
# The gateway owns its control and static URLs. The instance owns native management.
LOCAL_NAMESPACES = {
    "__mower",
    "admin",
    "assets",
    "dialog",
    "instances",
    "relay",
}
LOCAL_PATHS = {
    "/import",
    "/config-backup/import",
    "/config-profiles/import",
    "/process-control/action",
    "/resource/install",
    "/resource-update/manual",
}
MAINTENANCE_NAMESPACES = {"software-update", "maa-update", "maa-resource-update"}


def allowed_request(method, target):
    if not isinstance(method, str) or method not in HTTP_METHODS:
        return False
    if not isinstance(target, str) or len(target) > 8192:
        return False
    if not target.startswith("/") or target.startswith("//") or "#" in target:
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in target):
        return False
    try:
        url = urlsplit(target)
        path = unquote(url.path, errors="strict")
    except ValueError:
        return False
    # Permit encoded names inside a segment, but never encoded URL delimiters.
    if len(path.split("/")) != len(url.path.split("/")) or any(
        c in path for c in "\\%?#"
    ):
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        return False
    if "//" in path or any(part in {".", ".."} for part in path.split("/")):
        return False
    path = path.rstrip("/")
    namespace = path.partition("/")[2].partition("/")[0]
    if (
        not path
        or namespace in LOCAL_NAMESPACES
        or path in LOCAL_PATHS
        or path in SOCKETS
    ):
        return False
    if path.startswith("/software-update/source/"):
        return False
    if namespace in MAINTENANCE_NAMESPACES and method not in {"GET", "HEAD"}:
        return False
    return True


def decode_body(value):
    if not isinstance(value, str) or len(value) > (MAX_BODY + 2) // 3 * 4:
        raise ValueError("中转数据超过大小限制")
    data = base64.b64decode(value, validate=True)
    if len(data) > MAX_BODY:
        raise ValueError("中转数据超过大小限制")
    return data


def response_kind(path):
    path = urlsplit(path).path
    if path.startswith("/screenshots/") or path in {
        "/latest-screenshot",
        "/device/performance-test/screenshot",
    }:
        return "image"
    if path.endswith("/export") or path in {
        "/diagnostics/export",
        "/export-json",
        "/config-backup/export",
    }:
        return "attachment"
    return "data"


def validate_response(path, status, mime, data, *, method=None):
    if (
        type(status) is not int
        or not 200 <= status <= 599
        or len(data) > MAX_BODY
        or not isinstance(mime, str)
        or len(mime) > 128
    ):
        raise ValueError("中转响应无效")
    if method == "HEAD":
        if data or not re.fullmatch(r"[a-zA-Z0-9.+-]+/[a-zA-Z0-9.+-]+", mime):
            raise ValueError("中转 HEAD 响应无效")
        return
    if status == 204 and not data:
        return
    if urlsplit(path).path == "/gui/log-background" and status == 200:
        if mime == "image/webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return
        raise ValueError("日志背景图格式无效")
    kind = response_kind(path)
    if kind == "image" and status < 400:
        if mime == "image/jpeg" and data.startswith(b"\xff\xd8\xff"):
            return
        if mime == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
            return
        raise ValueError("中转只接受 Mower 截图格式")
    if (
        kind == "attachment"
        and status < 400
        and mime
        in {
            "application/zip",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        and data.startswith(b"PK")
    ):
        return
    if mime == "application/json":
        json.loads(data)
        return
    if mime == "text/plain" and len(data) <= 65536:
        data.decode("utf-8")
        return
    raise ValueError("中转不接受网页或脚本响应")
