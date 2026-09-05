"""Shared network settings for desktop and web deployments."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests
from flask import Blueprint, abort, current_app, request

from arknights_mower.utils import network_settings
from arknights_mower.utils.github_download import download_url

network_bp = Blueprint("network", __name__, url_prefix="/network")
API_TEST_URL = "https://api.github.com/repos/ArkMowers/arknights-mower"
FILE_TEST_URL = (
    "https://raw.githubusercontent.com/ArkMowers/MowerResource/main/version.json"
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


def _probe_connection(label, url, proxy, key, expected=None):
    started = time.monotonic()
    result = {"label": label, "ok": False}
    try:
        # A fixed public endpoint, with no Mower token or AI credentials forwarded.
        with requests.Session() as client:
            client.trust_env = False
            if proxy:
                client.proxies = {"http": proxy, "https": proxy}
            with client.get(url, timeout=(3, 6), stream=True) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_content(8192):
                    if time.monotonic() - started > 10:
                        raise requests.Timeout()
                    body.extend(chunk)
                    if len(body) > 128 * 1024:
                        raise ValueError("测试响应过大")
                payload = json.loads(body)
                if not isinstance(payload, dict) or not isinstance(
                    payload.get(key), str
                ):
                    raise ValueError("测试地址返回的内容不正确")
                if expected is not None and payload[key] != expected:
                    raise ValueError("测试地址返回的内容不正确")
        result.update(ok=True, message="连接成功")
    except requests.Timeout:
        result["message"] = "连接超时，请检查代理地址和网络"
    except requests.exceptions.ProxyError:
        result["message"] = "无法连接代理，请检查代理服务是否开启"
    except (requests.RequestException, ValueError):
        result["message"] = "连接失败或返回内容异常，请检查代理设置"
    result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    return result


@network_bp.post("/test")
def test_connections():
    settings = network_settings.get_effective_settings()
    targets = (
        ("网络连接", API_TEST_URL, "full_name", "ArkMowers/arknights-mower"),
        (
            "GitHub 文件下载",
            download_url(FILE_TEST_URL, settings["github_proxy"]),
            "res_version",
            None,
        ),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                _probe_connection,
                label,
                url,
                network_settings.proxy_for_url(url),
                key,
                expected,
            )
            for label, url, key, expected in targets
        ]
        results = [future.result() for future in futures]
    return {"ok": True, "settings": settings, "results": results}


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
