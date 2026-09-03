"""手动更新包识别与应用。"""

from collections.abc import Callable
from io import BytesIO
from zipfile import ZipFile

from arknights_mower.utils import hot_update
from arknights_mower.utils.resource_pkg import (
    _RESOURCE_MARKER,
    install_resource_pkg,
)

BusyCheck = Callable[[], dict | None]


def apply_manual_update(data: bytes, busy_check: BusyCheck | None = None) -> dict:
    """识别并应用热更包或资源包，返回可直接作为接口响应的字典。"""
    try:
        with ZipFile(BytesIO(data)) as z:
            names = z.namelist()
    except Exception:
        return {"ok": False, "kind": "unknown", "message": "不是有效的 zip 包"}

    if hot_update._has_hotupdate_marker(names):
        if hot_update.apply_manual_zip(data):
            return {"ok": True, "kind": "hot_update", "message": "热更包已应用"}
        return {
            "ok": False,
            "kind": "hot_update",
            "message": "热更包应用失败（请确认是有效的 hot_update.zip）",
        }

    if _RESOURCE_MARKER in names:
        if busy_check is not None and (busy := busy_check()):
            return {**busy, "kind": "resource"}
        if install_resource_pkg(data):
            return {
                "ok": True,
                "kind": "resource",
                "message": "资源包安装成功，重启后完全生效",
            }
        return {
            "ok": False,
            "kind": "resource",
            "message": "资源包安装失败（已回滚）",
        }

    return {
        "ok": False,
        "kind": "unknown",
        "message": "无法识别的更新包（热更包需 nav_steps.json，资源包需 version.json）",
    }
