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


def allowed_request(method, target):
    if not isinstance(target, str) or len(target) > 8192:
        return False
    try:
        url = urlsplit(target)
    except ValueError:
        return False
    if url.scheme or url.netloc or url.fragment or not target.startswith("/"):
        return False
    path = unquote(url.path)
    if path != url.path or "\\" in path or "//" in path:
        return False
    if any(part in {".", ".."} for part in path.split("/")):
        return False
    return any(
        method in methods and re.fullmatch(pattern, path)
        for methods, pattern in HTTP_OPERATIONS
    )


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


def validate_response(path, status, mime, data):
    if (
        type(status) is not int
        or not 200 <= status <= 599
        or len(data) > MAX_BODY
        or not isinstance(mime, str)
        or len(mime) > 128
    ):
        raise ValueError("中转响应无效")
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
    if kind == "attachment" and status < 400:
        return
    if mime == "application/json":
        json.loads(data)
        return
    if mime == "text/plain" and len(data) <= 65536:
        data.decode("utf-8")
        return
    raise ValueError("中转不接受网页或脚本响应")


HTTP_OPERATIONS = [
    (("GET",), "/basement-skill/operators"),
    (("GET",), "/check-maa"),
    (("GET",), "/check-maa/status"),
    (("GET",), "/check-skland"),
    (("GET",), "/check-skland-sign"),
    (("GET", "PATCH", "POST"), "/conf"),
    (("GET",), "/config-backup/export"),
    (("GET",), "/config-profiles"),
    (("GET",), "/gui/appearance"),
    (("GET",), "/gui/log-background"),
    (("GET",), "/db-admin/maintenance"),
    (("GET",), "/process-control/info"),
    (("GET",), "/gui/sidebar"),
    (("GET",), "/daily-status"),
    (("GET",), "/crash-recovery/status"),
    (("GET",), "/cultivate-fetch"),
    (("POST",), "/db-admin/delete"),
    (("GET",), "/db-admin/stats"),
    (("GET",), "/depot/history"),
    (("GET",), "/depot/readdepot"),
    (("POST",), "/device/avd/start"),
    (("POST",), "/device/boss_key"),
    (("POST",), "/device/discover"),
    (("POST",), "/device/genymotion/start"),
    (("DELETE", "GET", "POST"), "/device/performance-test"),
    (("GET",), "/device/performance-test/screenshot"),
    (("POST",), "/device/preflight"),
    (("POST",), "/device/redroid/start"),
    (("POST",), "/device/start"),
    (("GET",), "/device/status"),
    (("GET",), "/diagnostics/errors"),
    (("DELETE",), "/diagnostics/errors/[A-Za-z0-9_.-]+"),
    (("POST",), "/diagnostics/errors/[A-Za-z0-9_.-]+/analyze"),
    (("GET",), "/diagnostics/errors/[A-Za-z0-9_.-]+/export"),
    (("GET",), "/diagnostics/errors/[A-Za-z0-9_.-]+/logs"),
    (("GET",), "/diagnostics/export"),
    (("GET",), "/diagnostics/timeline"),
    (("GET",), "/export-json"),
    (("GET",), "/facility-state"),
    (("GET",), "/getwatermark"),
    (("POST",), "/growth-chip-farming"),
    (("DELETE", "GET", "PUT"), "/growth-crafting-order"),
    (("GET", "POST"), "/growth-plan"),
    (("GET",), "/growth-survey"),
    (("POST",), "/growth-sync"),
    (("DELETE", "GET", "PUT"), "/growth-sync-token"),
    (("GET",), "/item"),
    (("GET",), "/latest-screenshot"),
    (("GET",), "/maa-conn-preset"),
    (("GET",), "/maa-resource-update/info"),
    (("GET",), "/maa-resource-update/status"),
    (("GET",), "/maa-update/info"),
    (("GET",), "/maa-update/status"),
    (("GET",), "/mastery-recommendation"),
    (("GET",), "/mastery-recommendation-debug"),
    (("POST",), "/mastery-t3-debug"),
    (("POST",), "/mastery-t3-summary"),
    (("GET",), "/network/maa-copilot/[0-9]+"),
    (("GET", "POST"), "/network/settings"),
    (("POST",), "/network/test"),
    (("GET",), "/operator"),
    (("GET", "POST"), "/plan"),
    (("POST",), "/plan/restore-running"),
    (("DELETE",), "/record/clear-data"),
    (("GET",), "/record/getMoodRatios"),
    (("GET",), "/record/mood-available-operators"),
    (("GET",), "/record/mood-series"),
    (("GET",), "/report/getOrundumData"),
    (("GET",), "/report/getReportData"),
    (("GET",), "/report/recycling_history"),
    (("GET",), "/report/recycling_history/export"),
    (("DELETE", "GET", "PUT"), "/report/recycling_settings"),
    (("POST",), "/report/recycling_settings/import"),
    (("GET",), "/report/restore-trading-history"),
    (("GET",), "/report/trading_history"),
    (("GET", "POST"), "/rescue-plan"),
    (("POST",), "/rescue-plan/validate"),
    (("GET",), "/resource-version"),
    (("GET",), "/resource/status"),
    (("GET",), "/riic/income-cache"),
    (("DELETE", "PUT"), "/scheduled-start"),
    (("GET",), "/screenshot/latest"),
    (("GET",), "/screenshot/stats"),
    (("GET",), r"/screenshots/[A-Za-z0-9_./-]+\.(?:jpg|jpeg|png)"),
    (("GET",), "/shop"),
    (("GET", "POST"), "/sss-copilot"),
    (("GET",), "/stage/inventory-rules"),
    (("GET",), "/stage/latest-activity"),
    (("GET", "POST"), "/start/[A-Za-z0-9_.-]+"),
    (("GET",), "/status"),
    (("GET",), "/stop"),
    (("GET",), "/stop-maa"),
    (("POST",), "/submit_feedback"),
    (("GET", "POST"), "/task"),
    (("GET",), "/test-custom-screenshot"),
    (("GET",), "/test-email"),
    (("GET", "POST"), "/ui-state/log-layout"),
    (("GET", "PATCH", "POST"), "/ui-state/mood-board"),
    (("GET",), "/update-notice"),
    (("POST",), "/update-notice/ack"),
    (("POST",), "/validate-plan"),
    (("GET",), "/weekly-plans"),
    (("DELETE",), "/weekly-plans/[A-Za-z0-9_.-]+"),
    (("POST",), "/weekly-plans/active"),
    (("POST",), "/weekly-plans/activity-fallback"),
    (("POST",), "/workshop-auto-config"),
    (("GET",), "/workshop-preset"),
    (("GET",), "/workshop-status"),
]
