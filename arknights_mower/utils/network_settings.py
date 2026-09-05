"""Shared proxy settings for subsequent requests and newly launched children."""

import json
import logging
import os
import threading
import urllib.request
from urllib.parse import urlsplit

from arknights_mower.utils.github_download import normalize_proxy
from arknights_mower.utils.path import get_path
from arknights_mower.utils.update_runtime import write_json

_PROXY_ENV_KEYS = (
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "all_proxy",
    "ALL_PROXY",
)
_ENV_KEYS = (
    *_PROXY_ENV_KEYS,
    "no_proxy",
    "NO_PROXY",
    "OPENAI_PROXY",
)
_BASE_ENV_KEY = "MOWER_PROXY_BASE_ENV"
_base_environment = None
_last_proxy = None
_environment_lock = threading.RLock()
_effective_settings = None
_sync_thread = None
_sync_stop = threading.Event()


def settings_path():
    return get_path("@app/config/network.json", space="")


def normalize_http_proxy(value):
    if not isinstance(value, str):
        raise ValueError("全局网络代理地址必须是字符串")
    value = value.strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in ("http", "https")
            and parsed.hostname
            and parsed.port != 0
            and not parsed.username
            and not parsed.password
            and parsed.path in ("", "/")
            and not parsed.query
            and not parsed.fragment
            and not any(c.isspace() or ord(c) < 32 for c in value)
            and "\\" not in value
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("全局网络代理请填写 HTTP(S) 地址，例如 http://127.0.0.1:7897")
    return value.rstrip("/")


def get_settings():
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        return {
            "http_proxy": normalize_http_proxy(data.get("http_proxy", "")),
            "github_proxy": normalize_proxy(data.get("github_proxy", "")),
        }
    except (OSError, ValueError, AttributeError):
        return {"http_proxy": "", "github_proxy": ""}


def save_settings(data):
    settings = {
        "http_proxy": normalize_http_proxy(data["http_proxy"]),
        "github_proxy": normalize_proxy(data["github_proxy"]),
    }
    with _environment_lock:
        apply_http_proxy()
        write_json(settings_path(), settings)
        apply_http_proxy()
    return settings


def apply_http_proxy():
    """Refresh environment defaults without interrupting in-flight requests.

    Keep the launch environment through restarts so clearing a saved override
    restores the original proxy instead of inheriting the previous override.
    """
    global _base_environment, _last_proxy, _effective_settings
    with _environment_lock:
        if _base_environment is None:
            try:
                baseline = json.loads(os.environ.get(_BASE_ENV_KEY, "null"))
                if not isinstance(baseline, dict) or any(
                    baseline.get(key) is not None and not isinstance(baseline[key], str)
                    for key in _ENV_KEYS
                ):
                    baseline = None
            except ValueError:
                baseline = None
            _base_environment = {
                key: baseline.get(key) if baseline is not None else os.environ.get(key)
                for key in _ENV_KEYS
            }
            os.environ[_BASE_ENV_KEY] = json.dumps(_base_environment)
        settings = get_settings()
        if settings == _effective_settings:
            return
        proxy = settings["http_proxy"]
        for key, value in _base_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if proxy:
            for key in _PROXY_ENV_KEYS:
                os.environ[key] = proxy
            # LangChain otherwise lets OPENAI_PROXY override HTTP(S)/NO_PROXY.
            os.environ["OPENAI_PROXY"] = ""
        # Keep the web UI, local screenshot services and readiness checks local.
        if proxy or any(_base_environment[key] for key in _PROXY_ENV_KEYS):
            bypass = ",".join(
                filter(
                    None,
                    (
                        None if proxy else _base_environment["no_proxy"],
                        None if proxy else _base_environment["NO_PROXY"],
                        "localhost,127.0.0.1,::1",
                    ),
                )
            )
            os.environ["no_proxy"] = os.environ["NO_PROXY"] = bypass
        urllib.request.install_opener(urllib.request.build_opener())
        _last_proxy = proxy
        _effective_settings = settings


def get_effective_settings():
    with _environment_lock:
        apply_http_proxy()
        return dict(_effective_settings)


def proxy_for_url(url, *, ai=False):
    """Resolve a route at request time, including the launch environment fallback."""
    import requests

    with _environment_lock:
        apply_http_proxy()
        if (
            ai
            and os.environ.get("OPENAI_PROXY")
            and not requests.utils.should_bypass_proxies(
                url, no_proxy=os.environ.get("no_proxy", os.environ.get("NO_PROXY"))
            )
        ):
            return os.environ["OPENAI_PROXY"]
        proxies = requests.utils.get_environ_proxies(url)
        return proxies.get(urlsplit(url).scheme) or proxies.get("all")


def start_proxy_sync():
    """Keep requests/urllib and future subprocesses in other instances current."""
    global _sync_thread
    with _environment_lock:
        apply_http_proxy()
        if _sync_thread is not None and _sync_thread.is_alive():
            return
        _sync_stop.clear()

        def sync():
            while not _sync_stop.wait(0.5):
                try:
                    apply_http_proxy()
                except Exception:
                    logging.getLogger(__name__).exception("同步网络代理设置失败")

        _sync_thread = threading.Thread(
            target=sync, name="mower-proxy-sync", daemon=True
        )
        _sync_thread.start()
