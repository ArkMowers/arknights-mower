"""Shared network settings for desktop and web deployments."""

import time
from urllib.parse import urlparse

import requests
from flask import Blueprint, abort, current_app, request

from arknights_mower.utils import network_settings
from arknights_mower.utils.github_download import download_url

network_bp = Blueprint("network", __name__, url_prefix="/network")
FILE_TEST_URL = (
    "https://github.com/ArkMowers/MowerResource/releases/latest/download/resource.zip"
)


@network_bp.before_request
def authorize():
    if (
        hasattr(current_app, "token")
        and request.headers.get("token", "") != current_app.token
    ):
        abort(403)
    if request.method == "POST":
        if request.headers.get("X-Mower-Settings") != "1":
            abort(403)
        origin = request.headers.get("Origin")
        if origin and urlparse(origin).netloc != request.host:
            abort(403)


@network_bp.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "GET":
        return {"ok": True, **network_settings.get_settings()}
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not {"http_proxy", "github_proxy"} <= data.keys():
        return {"ok": False, "message": "请提供完整的网络代理设置"}, 400
    try:
        settings = network_settings.save_settings(data)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}, 400
    except OSError:
        return {"ok": False, "message": "代理设置保存失败，请检查配置目录权限"}, 500
    return {"ok": True, **settings}


def _probe_connection(label, url, proxy):
    started = time.monotonic()
    result = {"label": label, "ok": False}
    try:
        # A fixed public endpoint, with no Mower token or AI credentials forwarded.
        with requests.Session() as client:
            client.trust_env = False
            if proxy:
                client.proxies = {"http": proxy, "https": proxy}
            with client.head(url, timeout=(3, 6), allow_redirects=True) as response:
                response.raise_for_status()
        result.update(ok=True, message="连接成功")
    except requests.Timeout:
        result["message"] = "连接超时，请检查代理地址和网络"
    except requests.exceptions.ProxyError:
        result["message"] = "无法连接代理，请检查代理服务是否开启"
    except requests.RequestException:
        result["message"] = "连接失败，请检查代理设置或下载地址状态"
    result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    return result


@network_bp.post("/test")
def test_connections():
    """Probe the saved download route; callers save edited settings separately."""
    settings = network_settings.get_effective_settings()
    url = download_url(FILE_TEST_URL, settings["github_proxy"])
    result = _probe_connection(
        "GitHub 文件下载", url, network_settings.proxy_for_url(url)
    )
    return {"ok": True, "settings": settings, "results": [result]}


@network_bp.get("/maa-copilot/<int:code>")
def maa_copilot(code):
    """Fetch the fixed official endpoint through the same proxy as other MAA requests."""
    try:
        network_settings.apply_http_proxy()
        response = requests.get(f"https://prts.maa.plus/copilot/get/{code}", timeout=30)
        response.raise_for_status()
        data = response.json()
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("data"), dict)
            or not isinstance(data["data"].get("content"), str)
        ):
            raise ValueError("作业内容缺失")
        return data
    except (requests.RequestException, ValueError):
        return {
            "ok": False,
            "message": "MAA 作业下载失败，请检查作业编号和网络代理",
        }, 502
