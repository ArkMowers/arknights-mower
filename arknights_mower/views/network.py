"""Shared network settings for desktop and web deployments."""

import time
from urllib.parse import urlparse

import requests
from flask import Blueprint, abort, request

from arknights_mower.utils import network_settings
from arknights_mower.utils.github_download import (
    download_url,
    request_download,
    request_github,
)
from arknights_mower.utils.web_auth import check_request_origin, require_token

network_bp = Blueprint("network", __name__, url_prefix="/network")
FILE_TEST_URL = (
    "https://github.com/ArkMowers/MowerResource/releases/latest/download/resource.zip"
)


@network_bp.before_request
@require_token
def authorize():
    if request.method == "POST":
        if request.headers.get("X-Mower-Settings") != "1":
            abort(403)
        check_request_origin()


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
    except TimeoutError:
        return {"ok": False, "message": "网络配置正在保存，请稍后重试"}, 409
    except OSError:
        return {"ok": False, "message": "代理设置保存失败，请检查配置目录权限"}, 500
    return {"ok": True, **settings}


def _probe_connection(label, url, proxy, download_proxy=None, token=""):
    started = time.monotonic()
    result = {"label": label, "ok": False}
    try:
        # A fixed public endpoint, with no Mower token or AI credentials forwarded.
        with requests.Session() as client:
            client.trust_env = False
            if proxy:
                client.proxies = {"http": proxy, "https": proxy}
            response, selected_url = request_download(
                client,
                "head",
                url,
                proxy=download_proxy,
                token=token,
                timeout=(10, 10),
                allow_redirects=True,
            )
            with response:
                used_fallback = not download_proxy and selected_url != url
        result.update(
            ok=True,
            message=(
                f"默认站点 {urlparse(selected_url).hostname} 回退连接成功"
                if used_fallback
                else "连接成功"
            ),
        )
    except requests.ConnectTimeout:
        result["message"] = "建立连接超过 10 秒，请稍后重试或检查代理服务"
    except requests.ReadTimeout:
        result["message"] = "下载接口响应超过 10 秒，请稍后重试"
    except requests.Timeout:
        result["message"] = "连接测试超时，请稍后重试或检查网络"
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
    result = _probe_connection(
        "GitHub 文件下载",
        FILE_TEST_URL,
        network_settings.proxy_for_url(
            download_url(
                FILE_TEST_URL, settings["github_proxy"], token=settings["github_token"]
            )
        ),
        settings["github_proxy"],
        settings["github_token"],
    )
    results = [result]
    if settings["github_token"]:
        started = time.monotonic()
        validation = {"label": "GitHub Token", "ok": False}
        try:
            with request_github(
                requests,
                "get",
                "https://api.github.com/repos/ArkMowers/MowerResource",
                token=settings["github_token"],
                timeout=(10, 10),
            ) as response:
                if response.status_code == 401:
                    validation["message"] = "Token 无效或已过期，请重新生成"
                elif response.status_code in (403, 429):
                    validation["message"] = (
                        "GitHub 拒绝请求或额度已用尽，请检查 Token 权限和配额"
                    )
                else:
                    response.raise_for_status()
                    validation.update(ok=True, message="GitHub Token 认证成功")
        except requests.RequestException:
            validation["message"] = "无法验证 GitHub Token，请检查网络代理或稍后重试"
        validation["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        results.append(validation)
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


@network_bp.get("/maa-copilot-set/<int:code>")
def maa_copilot_set(code):
    """Read ordered operation-set members from the fixed public endpoint."""
    try:
        network_settings.apply_http_proxy()
        response = requests.get(
            "https://prts.maa.plus/set/get", params={"id": code}, timeout=30
        )
        response.raise_for_status()
        data = response.json()
        if (
            not isinstance(data, dict)
            or data.get("status_code", 200) != 200
            or not isinstance(data.get("data"), dict)
        ):
            raise ValueError("作业集内容缺失")
        ids = data["data"].get("copilot_ids")
        if (
            not isinstance(ids, list)
            or not ids
            or any(type(item) is not int or item <= 0 for item in ids)
        ):
            raise ValueError("作业集为空或包含无效作业编号")
        if len(ids) > 32:
            return {
                "ok": False,
                "message": "作业集超过队列的 32 项上限，请拆分后导入",
            }, 400
        return {"ids": [str(item) for item in ids]}
    except (requests.RequestException, ValueError):
        return {
            "ok": False,
            "message": "MAA 作业集读取失败，请检查作业集编号、公开状态和网络代理",
        }, 502
