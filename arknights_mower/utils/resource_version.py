"""资源包 version.json 的客户端读取与更新检测。

- 只读正式 ``data/version.json``（安装状态由资源包管理），远端先拉 tmp 再比对，**不覆盖正式文件**。
- 展示用 ``display_version``（可读名+#MMDD），比较用 ``res_version``（日期+内容哈希，只升不降），两者分离。
- fetch 不抛异常、失败回退 tmp 缓存。
"""

import json
import math
from pathlib import Path

import requests

from arknights_mower import __version__
from arknights_mower.utils.github_download import request_download
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.res_version import display_version
from arknights_mower.utils.resource_pkg import resource_pkg_path
from arknights_mower.utils.resource_store import compatibility_error, resource_newer

RESOURCE_VERSION_URL = (
    "https://raw.githubusercontent.com/ArkMowers/MowerResource/main/version.json"
)
TMP_VERSION_PATH = get_path("@app/tmp/resource_version.json")


def _read_json(path: Path, expected_type: type = dict):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, expected_type) else None


def _read_local_version_json() -> dict | None:
    # 资源包目录会在运行期间被原子替换。每次读取都重新解析 overlay，避免首次启动
    # 尚未安装资源包时把内置 version.json 路径永久缓存到进程结束。
    return _read_json(resource_pkg_path("arknights_mower/data/version.json"))


def _read_local_activities() -> list[dict]:
    """从当前资源的关卡窗口合并活动作战时间，不使用商店关闭时间。"""
    stages = (
        _read_json(resource_pkg_path("arknights_mower/data/stage_data_full.json"), list)
        or []
    )
    activities = {}
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        name, window = stage.get("zoneNameSecond"), stage.get("endTs")
        if not isinstance(name, str) or not name or not isinstance(window, dict):
            continue
        start, end = window.get("startTs"), window.get("endTs")
        if (
            type(start) not in (int, float)
            or type(end) not in (int, float)
            or not math.isfinite(start)
            or not math.isfinite(end)
            or not 0 < start < end
        ):
            continue
        if name in activities:
            activity = activities[name]
            activity["time"] = min(activity["time"], start)
            activity["endTime"] = max(activity["endTime"], end)
        else:
            activities[name] = {"name": name, "time": start, "endTime": end}
    return sorted(activities.values(), key=lambda activity: activity["endTime"])


def _read_tmp_cache() -> dict | None:
    return _read_json(TMP_VERSION_PATH)


def _write_tmp_cache(data: dict) -> None:
    TMP_VERSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    TMP_VERSION_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _fetch_remote_version_json() -> dict | None:
    try:
        r, _ = request_download(requests, "get", RESOURCE_VERSION_URL, timeout=30)
        if r.status_code != 200:
            logger.warning(f"资源版本拉取失败: HTTP {r.status_code}")
            return None
        return _read_json_from_bytes(r.content)
    except Exception as e:
        logger.warning(f"资源版本拉取失败: {e}")
        return None


def _read_json_from_bytes(raw: bytes) -> dict | None:
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def check_resource_update(local_only: bool = False) -> dict:
    """拉远端 version.json 到 tmp、比对本地 res_version，返回展示与更新状态。

    ``local_only`` 只读本地已装版本、不触碰网络，用于常驻显示「当前版本」。
    """
    local = _read_local_version_json() or {}
    current_version = local.get("res_version") or ""
    current = {
        "current_version": current_version,
        "current_display": display_version(local) or "",
        "current_metadata": {
            "activity": local.get("activity") or {},
            "activities": _read_local_activities(),
            "gacha": local.get("gacha") or {},
            "last_updated": local.get("last_updated") or "",
        },
    }

    if local_only:
        return {
            **current,
            "remote_version": "",
            "remote_display": "",
            "update_available": None,
            "error": None,
        }

    remote = _fetch_remote_version_json()
    if remote is None:
        remote = _read_tmp_cache()
        if remote is None:
            return {
                **current,
                "remote_version": "",
                "remote_display": "",
                "update_available": None,
                "error": "网络错误：无法获取远程版本号",
            }
    else:
        _write_tmp_cache(remote)

    remote_version = remote.get("res_version") or ""
    if not remote_version:
        return {
            **current,
            "remote_version": "",
            "remote_display": display_version(remote) or "",
            "update_available": None,
            "error": "远程版本号缺失",
        }
    incompatible = compatibility_error(remote, __version__)
    return {
        **current,
        "remote_version": remote_version,
        "remote_display": display_version(remote) or "",
        "update_available": not incompatible
        and resource_newer(remote, local, allow_same_day=True),
        "error": incompatible,
    }
