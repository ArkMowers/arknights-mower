"""Shared proxy settings for subsequent requests and newly launched children."""

import errno
import json
import os
import threading
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

from arknights_mower.utils.github_download import normalize_proxy, normalize_token
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
)
_BASE_ENV_KEY = "MOWER_PROXY_BASE_ENV"
_base_environment = None
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
            parsed.scheme in ("http", "https", "socks5", "socks5h")
            and parsed.hostname
            and parsed.port != 0
            and (not parsed.scheme.startswith("socks") or parsed.port is not None)
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
        raise ValueError(
            "全局网络代理支持 http://、https://、socks5:// 和 socks5h://；"
            "SOCKS 代理请填写端口，例如 socks5h://127.0.0.1:7897"
        )
    return value.rstrip("/")


@contextmanager
def _settings_file_lock(timeout=3.0):
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.with_suffix(path.suffix + ".lock").open("a+b") as stream:
        if os.name == "nt" and os.fstat(stream.fileno()).st_size == 0:
            stream.write(b"\0")
            stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("网络配置正在保存，请稍后重试") from exc
                time.sleep(min(0.02, remaining))
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def get_settings(*, strict=False):
    try:
        try:
            data = json.loads(settings_path().read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("网络配置格式不正确")
        return {
            "http_proxy": normalize_http_proxy(data.get("http_proxy", "")),
            "github_proxy": normalize_proxy(data.get("github_proxy", "")),
            "github_token": normalize_token(data.get("github_token", "")),
        }
    except (OSError, ValueError, AttributeError):
        if strict:
            raise
        return {"http_proxy": "", "github_proxy": "", "github_token": ""}


def save_settings(data, *, original=None):
    settings = {
        "http_proxy": normalize_http_proxy(data["http_proxy"]),
        "github_proxy": normalize_proxy(data["github_proxy"]),
    }
    if "github_token" in data:
        settings["github_token"] = normalize_token(data["github_token"])
    with _environment_lock, _settings_file_lock():
        current = get_settings(strict=True) if original is not None else get_settings()
        if original is not None and current != original:
            raise ValueError("网络配置已变化，请重新加载")
        settings.setdefault("github_token", current["github_token"])
        apply_http_proxy()
        write_json(settings_path(), settings)
        apply_http_proxy()
    return settings


def apply_http_proxy():
    """Refresh environment defaults without interrupting in-flight requests.

    Keep the launch environment through restarts so clearing a saved override
    restores the original proxy instead of inheriting the previous override.
    """
    global _base_environment, _effective_settings
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
        _effective_settings = settings


def get_effective_settings():
    with _environment_lock:
        apply_http_proxy()
        return dict(_effective_settings)


def proxy_for_url(url):
    """Resolve a route at request time, including the launch environment fallback."""
    import requests

    with _environment_lock:
        apply_http_proxy()
        proxies = requests.utils.get_environ_proxies(url)
        return proxies.get(urlsplit(url).scheme) or proxies.get("all")


def start_proxy_sync():
    """Keep the proxy environment in other instances and future children current."""
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
                    from arknights_mower.utils.log import logger

                    logger.exception("同步网络代理设置失败")

        _sync_thread = threading.Thread(
            target=sync, name="mower-proxy-sync", daemon=True
        )
        _sync_thread.start()
