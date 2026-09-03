import json
from datetime import datetime, timedelta
from io import BytesIO
from shutil import rmtree
from zipfile import ZipFile

import requests

from arknights_mower.utils import config
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.res_version import version_newer
from arknights_mower.utils.zip_safe import is_unsafe_zip_member

extract_path = get_path("@install/tmp/hot_update")
version_state = get_path("@install/tmp/hot_update_version.json")
HOT_UPDATE_REPO = "ArkMowers/MowerHotUpdate"

last_update = None


def _latest_release_tag() -> str | None:
    """取 GitHub Releases 最新的 tag_name；任何失败返回 None（不崩溃）。"""
    try:
        r = requests.get(
            f"https://api.github.com/repos/{HOT_UPDATE_REPO}/releases/latest",
            timeout=30,
        )
        if r.status_code != 200:
            logger.warning(f"获取热更新最新版本失败：HTTP {r.status_code}")
            return None
        return r.json().get("tag_name")
    except Exception as e:
        logger.warning(f"获取热更新最新版本失败：{e}")
        return None


def _read_applied_tag() -> str:
    """读本地已应用的热更版本；没有则返回空串。"""
    try:
        return version_state.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write_applied_tag(tag: str) -> None:
    """记录已应用的热更版本（独立于热更解压目录，不怕被 rmtree）。"""
    version_state.parent.mkdir(parents=True, exist_ok=True)
    version_state.write_text(tag, encoding="utf-8")


# 有效热更包的数据标记（zip 根目录）。version.json 只是可选版本清单，不单独算有效包。
_HOTUPDATE_MARKERS = ("nav_steps.json", "stage_data.json")


def _has_hotupdate_marker(names: list[str]) -> bool:
    """zip 根目录至少要带一个热更数据文件（nav_steps.json / stage_data.json）。"""
    return any(n in _HOTUPDATE_MARKERS for n in names)


def _extract_zip(data: bytes) -> bool:
    """核心应用路径：清空热更目录 -> 校验 zip 合法 + 热更标记 + zip-slip -> 解压。"""
    try:
        with ZipFile(BytesIO(data)) as z:
            names = z.namelist()
            if not _has_hotupdate_marker(names):
                logger.warning(
                    f"不是有效的热更包（缺 {_HOTUPDATE_MARKERS} 任一）：{names}"
                )
                return False
            if any(is_unsafe_zip_member(n) for n in names):
                logger.warning(f"热更包含非法路径，拒绝应用：{names}")
                return False
            if extract_path.exists():
                rmtree(extract_path)
            z.extractall(extract_path)
        return True
    except Exception as e:
        logger.exception(f"热更新应用失败：{e}")
        return False


def _version_tag_from_zip(data: bytes) -> str | None:
    """手动包的版本号尽力从 zip 内 version.json 读一个字符串；缺省/损坏/取不到返回 None。"""
    try:
        with ZipFile(BytesIO(data)) as z:
            if "version.json" not in z.namelist():
                return None
            raw = json.loads(z.read("version.json"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    for key in ("version", "version_name", "resource_version"):
        v = raw.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def apply_manual_zip(data: bytes) -> bool:
    """手动应用一份 hot_update.zip 内容：校验 + 解压到热更目录 + 记录版本。

    与网络下载走同一套应用路径（_extract_zip）；版本号尽力从 version.json 读，
    没有则不覆盖已记录版本。记录版本遵守与 #183 相同的「只升不降」守卫——拖入更旧
    的包不覆盖已应用的更新版本。用于国内直连 GitHub 不稳时的人工兜底。
    """
    if not _extract_zip(data):
        return False
    tag = _version_tag_from_zip(data)
    if tag:
        local = _read_applied_tag()
        if version_newer(tag, local, require_v=True):
            _write_applied_tag(tag)
        else:
            logger.warning(
                f"手动热更包版本 {tag} 不新于已应用版本 {local or '无'}，保持已记录版本"
            )
    return True


def _download_and_extract() -> bool:
    """下载最新 release 的 hot_update.zip 并解压到热更目录；成功返回 True。"""
    url = (
        f"https://github.com/{HOT_UPDATE_REPO}/releases/latest/download/hot_update.zip"
    )
    try:
        r = requests.get(url, timeout=60)
        if r.status_code != 200:
            logger.warning(f"热更新下载失败：HTTP {r.status_code}")
            return False
        return _extract_zip(r.content)
    except Exception as e:
        logger.exception(f"热更新下载解压失败：{e}")
        return False


def update():
    """检查并应用热更：GitHub Releases latest 的 tag 与本地已应用版本比对。

    由 config.conf.hot_update.enable 控制（默认关）；保留 30 分钟节流。
    仅在发现新版本或检测失败时记录日志，其余情况静默返回。
    """
    global last_update

    if not config.conf.hot_update.enable:
        return

    if last_update and datetime.now() - last_update < timedelta(minutes=30):
        return

    remote_tag = _latest_release_tag()
    if remote_tag is None:
        logger.warning("未获取到最新版本号，本次跳过")
        return

    local_tag = _read_applied_tag()
    if not version_newer(remote_tag, local_tag, require_v=True):
        last_update = datetime.now()
        return

    logger.info(f"发现新热更版本 {remote_tag}（本地 {local_tag or '无'}），开始下载")
    if _download_and_extract():
        _write_applied_tag(remote_tag)
        logger.info("热更新成功")
        last_update = datetime.now()
    else:
        logger.error("热更新失败！")
