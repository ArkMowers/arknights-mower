"""资源包 overlay：文件解析 + 下载 + 原子安装（#191）。

- 资源包解压到可写 ``@install/tmp/resource/``（冻结 exe 下 ``__rootdir__`` 只读，原位替换不成立），
  各加载器经 ``resource_pkg_path`` 先查 overlay、回退内置 ``__rootdir__``。
- zip 内路径相对仓库根（``arknights_mower/data/X.json``、``ui/public/depot/X.webp``）。
- 安装走「原子换目录」：staging → resource，旧目录先挪走，失败回滚；version.json 随 zip
  在整目录内原子落位（资源全成功才版本生效，失败整体回滚）。
"""

import os
from io import BytesIO
from pathlib import Path
from shutil import rmtree
from zipfile import ZipFile

import requests

from arknights_mower import __rootdir__
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.zip_safe import is_unsafe_zip_member

RESOURCE_OVERLAY = get_path("@install/tmp/resource")
_STAGING = get_path("@install/tmp/resource_staging")
_OLD = get_path("@install/tmp/resource_old")
RESOURCE_REPO = "ArkMowers/MowerResource"
RESOURCE_ZIP_URL = (
    f"https://github.com/{RESOURCE_REPO}/releases/latest/download/resource.zip"
)
# 有效资源包的标记：zip 根相对路径里的 version.json
_RESOURCE_MARKER = "arknights_mower/data/version.json"
_PKG_PREFIX = "arknights_mower/"


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
    """校验资源包 zip -> 解压到 staging -> 原子换目录（失败回滚）。成功返回 True。"""
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
    if _OLD.exists():
        rmtree(_OLD, ignore_errors=True)
    logger.info(f"资源包安装成功：{RESOURCE_OVERLAY}")
    return True
