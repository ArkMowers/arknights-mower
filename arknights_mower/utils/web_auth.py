"""Shared Web UI credential checks for protected HTTP requests."""

import ipaddress
from functools import wraps
from urllib.parse import urlparse

from flask import abort, current_app, request
from werkzeug.exceptions import HTTPException


def check_token():
    if (
        hasattr(current_app, "token")
        and request.headers.get("token", "") != current_app.token
    ):
        abort(403)


def require_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        check_token()
        return f(*args, **kwargs)

    return decorated_function


def origin_allowed(origin):
    try:
        source = urlparse(origin)
        if (
            source.scheme not in {"http", "https"}
            or not source.hostname
            or source.username
            or source.password
            or source.path
            or source.params
            or source.query
            or source.fragment
        ):
            return False
        if source.netloc == request.host and source.scheme == request.scheme:
            return True
        checker = current_app.config.get("WEB_UI_ORIGIN_ALLOWED")
        return bool(
            checker
            and getattr(current_app, "token", "")
            and ipaddress.ip_address(request.remote_addr).is_loopback
            and checker(origin)
        )
    except (ValueError, TypeError):
        return False


def preflight_allowed():
    origin = request.headers.get("Origin")
    method = request.headers.get("Access-Control-Request-Method")
    if not origin or not origin_allowed(origin) or not method or method == "OPTIONS":
        return False
    try:
        current_app.url_map.bind_to_environ(request.environ).match(method=method)
    except HTTPException:
        return False
    return True
