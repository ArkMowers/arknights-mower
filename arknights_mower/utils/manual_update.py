"""手动更新包识别与应用。"""

from collections.abc import Callable
from io import BytesIO
from zipfile import ZipFile

from arknights_mower.utils.resource_pkg import (
    _RESOURCE_MARKER,
    install_resource_pkg,
)

BusyCheck = Callable[[], dict | None]


def apply_manual_update(data: bytes, busy_check: BusyCheck | None = None) -> dict:
    """识别并应用资源包，返回可直接作为接口响应的字典。"""
    try:
        with ZipFile(BytesIO(data)) as z:
            names = z.namelist()
    except Exception:
        return {"ok": False, "kind": "unknown", "message": "不是有效的 zip 包"}

    if _RESOURCE_MARKER in names:
        if busy_check is not None and (busy := busy_check()):
            return {**busy, "kind": "resource"}
        if install_resource_pkg(data):
            return {
                "ok": True,
                "kind": "resource",
                "restart_required": False,
                "message": "资源包已安装，各实例在任务间歇加载，无需重启 Mower",
            }
        return {
            "ok": False,
            "kind": "resource",
            "message": "资源包安装失败（已回滚）",
        }

    return {
        "ok": False,
        "kind": "unknown",
        "message": "无法识别的更新包（资源包需 arknights_mower/data/version.json）",
    }
