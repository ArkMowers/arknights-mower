"""资源包 overlay：文件解析 + 下载 + 原子安装（#191）。

- 资源包解压到可写 ``@app/tmp/resource/``（冻结 exe 下 ``__rootdir__`` 只读，原位替换不成立），
  各加载器经 ``resource_pkg_path`` 先查 overlay、回退内置 ``__rootdir__``。
- zip 内路径相对仓库根（``arknights_mower/data/X.json``、``ui/public/depot/X.webp``）。
- 安装走「原子换目录」：staging → resource，旧目录先挪走，失败回滚；version.json 随 zip
  在整目录内原子落位（资源全成功才版本生效，失败整体回滚）。
- 切换后刷新已登记的进程内 JSON/模型缓存；刷新失败时连同目录一起回滚，无需重启进程。
"""

import os
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from shutil import rmtree
from threading import RLock
from zipfile import ZipFile

import requests

from arknights_mower import __rootdir__
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.zip_safe import is_unsafe_zip_member

RESOURCE_OVERLAY = get_path("@app/tmp/resource")
_STAGING = get_path("@app/tmp/resource_staging")
_OLD = get_path("@app/tmp/resource_old")
RESOURCE_REPO = "ArkMowers/MowerResource"
RESOURCE_ZIP_URL = (
    f"https://github.com/{RESOURCE_REPO}/releases/latest/download/resource.zip"
)
# 有效资源包的标记：zip 根相对路径里的 version.json
_RESOURCE_MARKER = "arknights_mower/data/version.json"
_PKG_PREFIX = "arknights_mower/"
_install_lock = RLock()
_reload_callbacks: dict[str, Callable[[], None]] = {}


def register_resource_reload(callback: Callable[[], None]) -> Callable[[], None]:
    """登记一个资源包切换后的进程内缓存刷新函数。"""
    key = f"{callback.__module__}.{callback.__qualname__}"
    _reload_callbacks[key] = callback
    return callback


def reload_resource_caches() -> None:
    """刷新当前进程里已经加载过的资源数据；任一失败都向上抛出。"""
    for callback in tuple(_reload_callbacks.values()):
        callback()


def resource_pkg_path(rel: str) -> Path:
    """资源包 overlay 优先、回退内置。rel 为 zip 内相对仓库根路径（如 ``arknights_mower/data/X.json``）。"""
    p = RESOURCE_OVERLAY / rel
    if p.exists():
        return p
    builtin_rel = rel[len(_PKG_PREFIX) :] if rel.startswith(_PKG_PREFIX) else rel
    return Path(__rootdir__) / builtin_rel


def download_resource_pkg() -> bytes | None:
    try:
        r = requests.get(RESOURCE_ZIP_URL, timeout=60)
        if r.status_code != 200:
            logger.warning(f"资源包下载失败: HTTP {r.status_code}")
            return None
        return r.content
    except Exception as e:
        logger.warning(f"资源包下载失败: {e}")
        return None


def install_resource_pkg(data: bytes) -> bool:
    """原子安装资源包并刷新进程内缓存；切换或加载失败均回滚。"""
    with _install_lock:
        try:
            with ZipFile(BytesIO(data)) as z:
                names = z.namelist()
                if _RESOURCE_MARKER not in names:
                    logger.warning(
                        f"不是有效的资源包（缺 {_RESOURCE_MARKER}）：{names[:5]}"
                    )
                    return False
                if any(is_unsafe_zip_member(n) for n in names):
                    logger.warning(f"资源包含非法路径，拒绝应用：{names[:5]}")
                    return False
                if _STAGING.exists():
                    rmtree(_STAGING)
                if _OLD.exists():
                    rmtree(_OLD)
                z.extractall(_STAGING)
        except Exception as e:
            logger.exception(f"资源包解压失败：{e}")
            return False

        try:
            if RESOURCE_OVERLAY.exists():
                os.replace(RESOURCE_OVERLAY, _OLD)
            os.replace(_STAGING, RESOURCE_OVERLAY)
        except Exception as e:
            logger.exception(f"资源包安装失败：{e}")
            if _OLD.exists() and not RESOURCE_OVERLAY.exists():
                try:
                    os.replace(_OLD, RESOURCE_OVERLAY)
                except Exception as e2:
                    logger.error(f"资源包回滚失败：{e2}")
            rmtree(_STAGING, ignore_errors=True)
            return False

        try:
            reload_resource_caches()
        except Exception as e:
            logger.exception(f"资源包进程内加载失败，正在回滚：{e}")
            try:
                if RESOURCE_OVERLAY.exists():
                    os.replace(RESOURCE_OVERLAY, _STAGING)
                if _OLD.exists():
                    os.replace(_OLD, RESOURCE_OVERLAY)
                reload_resource_caches()
            except Exception as rollback_error:
                logger.exception(f"资源包回滚后重新加载失败：{rollback_error}")
            rmtree(_STAGING, ignore_errors=True)
            return False

        if _OLD.exists():
            rmtree(_OLD, ignore_errors=True)
        logger.info(f"资源包安装成功并已在当前进程生效：{RESOURCE_OVERLAY}")
        return True
