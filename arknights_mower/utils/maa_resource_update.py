"""macOS 与 Linux 的 MaaResource 独立更新支持。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile, ZipInfo

import requests

from arknights_mower.utils.maa_update import (
    MaaUpdateError,
    backup_path_for,
    has_maa_installation,
    mirrorchyan_sp_id,
    replace_with_backup,
)
from arknights_mower.utils.zip_safe import is_unsafe_zip_member

GITHUB_RESOURCE_VERSION_URL = (
    "https://raw.githubusercontent.com/"
    "MaaAssistantArknights/MaaResource/main/resource/version.json"
)
GITHUB_RESOURCE_ARCHIVE_URL = (
    "https://github.com/MaaAssistantArknights/MaaResource/archive/refs/heads/main.zip"
)
MIRRORCHYAN_RESOURCE_API = "https://mirrorchyan.com/api/resources/MaaResource/latest"
REQUEST_TIMEOUT = (10, 60)
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
MAX_RESOURCE_FILES = 100_000
MAX_RESOURCE_SIZE = 2 * 1024 * 1024 * 1024
RESOURCE_VERSION_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

ProgressCallback = Callable[[str, int, int, str], None]

_MIRRORCHYAN_ERRORS = {
    1001: "Mirror酱请求参数错误",
    7001: "Mirror酱 CDK 已过期，请使用新的 CDK。",
    7002: "Mirror酱 CDK 无效，请检查输入是否正确。",
    7003: "Mirror酱 CDK 今日下载次数已达上限。",
    7004: "Mirror酱 CDK 与 MaaResource 不匹配。",
    7005: "Mirror酱 CDK 已失效（已被封禁）。",
    8001: "Mirror酱中没有 MaaResource 资源",
}


@dataclass(frozen=True)
class MaaResourceRelease:
    version: str
    source: str
    url: str = ""
    size: int = 0
    sha256: str = ""
    release_note: str = ""
    available: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "source": self.source,
            "release_note": self.release_note,
            "available": self.available,
        }


def _emit(
    callback: ProgressCallback | None,
    phase: str,
    current: int,
    total: int,
    message: str,
) -> None:
    if callback is not None:
        callback(phase, current, total, message)


def parse_resource_version(value: str) -> datetime:
    """把 MaaResource ``last_updated`` 解析为 UTC 时间。"""
    try:
        return datetime.strptime(value, RESOURCE_VERSION_FORMAT).replace(
            tzinfo=timezone.utc
        )
    except (TypeError, ValueError):
        raise MaaUpdateError("Maa 资源版本格式无效") from None


def _resource_info_from_payload(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise MaaUpdateError("Maa 资源版本文件格式无效")
    version = payload.get("last_updated")
    if not isinstance(version, str) or not version.strip():
        raise MaaUpdateError("Maa 资源版本文件缺少 last_updated")
    version = version.strip()
    parse_resource_version(version)
    activity = payload.get("activity")
    activity_name = activity.get("name") if isinstance(activity, dict) else ""
    return {
        "version": version,
        "release_note": activity_name if isinstance(activity_name, str) else "",
    }


def read_maa_resource_info(target: Path | str) -> dict[str, str]:
    """读取安装目录中 ``resource/version.json`` 的资源版本。"""
    version_file = Path(target).expanduser() / "resource" / "version.json"
    try:
        payload = json.loads(version_file.read_text(encoding="utf-8"))
        return _resource_info_from_payload(payload)
    except (OSError, json.JSONDecodeError, MaaUpdateError):
        return {"version": "", "release_note": ""}


def resource_backup_path(target: Path | str) -> Path:
    return backup_path_for(Path(target).expanduser() / "resource")


def get_github_resource_release(
    session: requests.Session | None = None,
) -> MaaResourceRelease:
    """读取 MaaResource main 分支的最新资源版本。"""
    client = session or requests.Session()
    try:
        response = client.get(GITHUB_RESOURCE_VERSION_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        info = _resource_info_from_payload(response.json())
    except MaaUpdateError:
        raise
    except (requests.RequestException, ValueError):
        raise MaaUpdateError("获取最新 Maa 资源版本失败") from None
    return MaaResourceRelease(
        version=info["version"],
        source="github",
        url=GITHUB_RESOURCE_ARCHIVE_URL,
        release_note=info["release_note"],
    )


def _mirrorchyan_error(code: int) -> str:
    return _MIRRORCHYAN_ERRORS.get(code, "Mirror酱服务返回业务错误")


def get_mirrorchyan_resource_release(
    token: str,
    current_version: str = "",
    session: requests.Session | None = None,
) -> MaaResourceRelease:
    """通过 Mirror酱检查 MaaResource 增量更新。"""
    token = token.strip()
    if not token:
        raise MaaUpdateError("请填写 Mirror酱 CDK")
    if current_version:
        parse_resource_version(current_version)
    client = session or requests.Session()
    params = {
        "current_version": current_version or "1970-01-01 00:00:00.000",
        "cdk": token,
        "user_agent": "arknights_mower",
        "sp_id": mirrorchyan_sp_id(),
    }
    try:
        response = client.get(
            MIRRORCHYAN_RESOURCE_API,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        # requests 的异常可能包含带 CDK 的完整 URL，不向上回显原异常。
        raise MaaUpdateError("连接 Mirror酱服务失败") from None
    if not isinstance(payload, dict):
        raise MaaUpdateError("Mirror酱返回了无效数据")
    try:
        code = int(payload.get("code"))
    except (TypeError, ValueError):
        raise MaaUpdateError("Mirror酱返回了无效状态码") from None
    if code != 0:
        raise MaaUpdateError(_mirrorchyan_error(code))
    data = payload.get("data")
    if not isinstance(data, dict):
        raise MaaUpdateError("Mirror酱返回的 MaaResource 信息不完整")
    expires_at = data.get("cdk_expired_time")
    try:
        normalized_expires_at = int(expires_at or 0)
    except (TypeError, ValueError):
        normalized_expires_at = 0
    if normalized_expires_at and normalized_expires_at <= int(time.time()):
        raise MaaUpdateError(_MIRRORCHYAN_ERRORS[7001])
    version = data.get("version_name")
    if not isinstance(version, str):
        raise MaaUpdateError("Mirror酱返回的 Maa 资源版本无效")
    version = version.strip()
    remote_time = parse_resource_version(version)
    available = not current_version or remote_time > parse_resource_version(
        current_version
    )
    url = data.get("url")
    if available:
        if not isinstance(url, str) or urlsplit(url).scheme != "https":
            raise MaaUpdateError("Mirror酱没有返回有效的 MaaResource 下载地址")
    else:
        url = ""
    size = data.get("filesize")
    try:
        normalized_size = max(int(size or 0), 0)
    except (TypeError, ValueError):
        normalized_size = 0
    checksum = data.get("sha256")
    release_note = data.get("release_note")
    return MaaResourceRelease(
        version=version,
        source="mirrorchyan",
        url=url,
        size=normalized_size,
        sha256=checksum if isinstance(checksum, str) else "",
        release_note=release_note if isinstance(release_note, str) else "",
        available=available,
    )


def get_maa_resource_release(
    source: str,
    current_version: str = "",
    mirror_token: str = "",
    session: requests.Session | None = None,
) -> MaaResourceRelease:
    """按所选更新源检查 MaaResource，并统一计算是否有新版本。"""
    client = session or requests.Session()
    if source == "mirrorchyan":
        return get_mirrorchyan_resource_release(
            mirror_token,
            current_version=current_version,
            session=client,
        )
    if source != "github":
        raise MaaUpdateError("未知的 Maa 资源更新源")
    release = get_github_resource_release(client)
    return replace(
        release,
        available=not current_version
        or parse_resource_version(release.version)
        > parse_resource_version(current_version),
    )


def download_resource_archive(
    release: MaaResourceRelease,
    destination: Path,
    session: requests.Session | None = None,
    callback: ProgressCallback | None = None,
) -> int:
    """流式下载 MaaResource ZIP，并校验可用的大小与 SHA-256。"""
    if not release.url:
        raise MaaUpdateError("没有可下载的 MaaResource 更新包")
    client = session or requests.Session()
    part_path = destination.with_suffix(destination.suffix + ".part")
    downloaded = 0
    digest = hashlib.sha256()
    try:
        with client.get(
            release.url,
            stream=True,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length") or release.size or 0)
            with part_path.open("wb") as target:
                for chunk in response.iter_content(DOWNLOAD_CHUNK_SIZE):
                    if not chunk:
                        continue
                    target.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    _emit(
                        callback,
                        "downloading",
                        downloaded,
                        total,
                        f"正在通过 {'Mirror酱' if release.source == 'mirrorchyan' else 'GitHub'}下载 Maa 资源包",
                    )
    except requests.RequestException:
        raise MaaUpdateError("下载 Maa 资源包失败") from None
    finally:
        if part_path.exists() and downloaded == 0:
            part_path.unlink()
    if release.size and downloaded != release.size:
        part_path.unlink(missing_ok=True)
        raise MaaUpdateError(f"Maa 资源包下载不完整：{downloaded}/{release.size} 字节")
    if release.sha256 and digest.hexdigest().lower() != release.sha256.lower():
        part_path.unlink(missing_ok=True)
        raise MaaUpdateError("Maa 资源包 SHA-256 校验失败")
    os.replace(part_path, destination)
    return downloaded


def _zip_info_is_symlink(info: ZipInfo) -> bool:
    return stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK


def _resource_relative_path(info: ZipInfo) -> PurePosixPath | None:
    path = PurePosixPath(info.filename)
    parts = path.parts
    if len(parts) >= 2 and parts[:2] == ("MaaResource-main", "resource"):
        return PurePosixPath(*parts[2:])
    if parts and parts[0] == "resource":
        return PurePosixPath(*parts[1:])
    return None


def _inspect_resource_archive(archive: ZipFile) -> tuple[str, list[ZipInfo]]:
    infos = archive.infolist()
    if len(infos) > MAX_RESOURCE_FILES:
        raise MaaUpdateError("Maa 资源包文件数量异常")
    if sum(info.file_size for info in infos) > MAX_RESOURCE_SIZE:
        raise MaaUpdateError("Maa 资源包解压后体积异常")
    resource_infos: list[ZipInfo] = []
    version_infos: list[ZipInfo] = []
    for info in infos:
        if is_unsafe_zip_member(info.filename):
            raise MaaUpdateError("Maa 资源包包含非法路径")
        if _zip_info_is_symlink(info):
            raise MaaUpdateError("Maa 资源包包含不支持的符号链接")
        relative = _resource_relative_path(info)
        if relative is None or not relative.parts:
            continue
        resource_infos.append(info)
        if relative == PurePosixPath("version.json"):
            version_infos.append(info)
    if len(version_infos) != 1:
        raise MaaUpdateError("Maa 资源包缺少唯一的 resource/version.json")
    try:
        payload = json.loads(archive.read(version_infos[0]).decode("utf-8"))
        version = _resource_info_from_payload(payload)["version"]
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
        raise MaaUpdateError("Maa 资源包中的 version.json 无效") from None
    return version, resource_infos


def _ensure_current_resource_tree_safe(current_resource: Path) -> None:
    if current_resource.is_symlink():
        raise MaaUpdateError("Maa resource 目录不能是符号链接")
    for path in current_resource.rglob("*"):
        if path.is_symlink():
            raise MaaUpdateError("Maa resource 目录包含不支持的符号链接")


def merge_resource_archive(
    archive_path: Path,
    current_resource: Path,
    staged_resource: Path,
    callback: ProgressCallback | None = None,
) -> str:
    """把增量资源覆盖到旧资源副本，返回包内资源版本。"""
    if not current_resource.is_dir():
        raise MaaUpdateError("Maa 安装目录中没有 resource 文件夹")
    _ensure_current_resource_tree_safe(current_resource)
    try:
        shutil.copytree(current_resource, staged_resource)
    except OSError as e:
        raise MaaUpdateError(f"复制现有 Maa 资源失败：{e}") from e
    try:
        with ZipFile(archive_path) as archive:
            version, infos = _inspect_resource_archive(archive)
            version_info = next(
                info
                for info in infos
                if _resource_relative_path(info) == PurePosixPath("version.json")
            )
            ordered = [info for info in infos if info is not version_info]
            ordered.append(version_info)
            files = [info for info in ordered if not info.is_dir()]
            file_index = 0
            for info in ordered:
                relative = _resource_relative_path(info)
                if relative is None:
                    continue
                destination = staged_resource.joinpath(*relative.parts)
                if info.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                file_index += 1
                _emit(
                    callback,
                    "merging",
                    file_index,
                    len(files),
                    "正在合并 Maa 增量资源",
                )
    except BadZipFile:
        raise MaaUpdateError("Maa 资源包不是有效的 ZIP") from None
    except (OSError, RuntimeError) as e:
        raise MaaUpdateError(f"合并 Maa 资源包失败：{e}") from e
    try:
        payload = json.loads(
            (staged_resource / "version.json").read_text(encoding="utf-8")
        )
        staged_info = _resource_info_from_payload(payload)
    except (OSError, json.JSONDecodeError, MaaUpdateError):
        staged_info = {"version": "", "release_note": ""}
    if staged_info["version"] != version:
        raise MaaUpdateError("合并后的 Maa 资源版本校验失败")
    return version


def install_maa_resource_update(
    target: Path | str,
    source: str = "github",
    mirror_token: str = "",
    system: str = "darwin",
    session: requests.Session | None = None,
    callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """检查并原子合并 MaaResource；Windows 由 Maa 主程序负责。"""
    system = system.lower()
    if system not in {"darwin", "linux"}:
        raise MaaUpdateError("当前平台请在 Maa 主程序中更新 Maa 资源")
    target_path = Path(target).expanduser()
    if not has_maa_installation(target_path):
        raise MaaUpdateError("请先下载并设置有效的 Maa 目录")
    resource_path = target_path / "resource"
    if not resource_path.is_dir():
        raise MaaUpdateError("Maa 安装目录中没有 resource 文件夹")
    if source not in {"github", "mirrorchyan"}:
        raise MaaUpdateError("未知的 Maa 资源更新源")

    current = read_maa_resource_info(target_path)
    _emit(callback, "checking", 0, 0, "正在检查 Maa 资源更新")
    client = session or requests.Session()
    release = get_maa_resource_release(
        source,
        current_version=current["version"],
        mirror_token=mirror_token,
        session=client,
    )
    if not release.available:
        return {
            "updated": False,
            "source": release.source,
            "version": current["version"] or release.version,
            "previous_version": current["version"],
            "release_note": release.release_note,
            "target": str(target_path),
            "backup": str(resource_backup_path(target_path)),
            "downloaded": 0,
        }

    with tempfile.TemporaryDirectory(
        prefix=".maa-resource-update-", dir=target_path
    ) as temp:
        work_dir = Path(temp)
        archive_path = work_dir / "MaaResource.zip"
        staged_resource = work_dir / "resource"
        downloaded = download_resource_archive(
            release,
            archive_path,
            session=client,
            callback=callback,
        )
        merged_version = merge_resource_archive(
            archive_path,
            resource_path,
            staged_resource,
            callback=callback,
        )
        if merged_version != release.version:
            raise MaaUpdateError("下载包与 Maa 资源版本信息不一致")
        _emit(callback, "installing", 0, 0, "正在切换 Maa 资源并保留回滚副本")
        try:
            backup = replace_with_backup(staged_resource, resource_path, work_dir)
        except OSError as e:
            raise MaaUpdateError(f"替换 Maa 资源目录失败：{e}") from e
        installed = read_maa_resource_info(target_path)
        if installed["version"] != release.version:
            failed_resource = work_dir / "failed-resource"
            previous_backup = work_dir / "previous.old"
            try:
                os.replace(resource_path, failed_resource)
                os.replace(backup, resource_path)
                if previous_backup.exists():
                    os.replace(previous_backup, backup)
            except OSError as e:
                raise MaaUpdateError(f"Maa 资源版本校验失败且回滚失败：{e}") from e
            raise MaaUpdateError("更新后重新读取 Maa 资源版本失败，已回滚")

    return {
        "updated": True,
        "source": release.source,
        "version": installed["version"],
        "previous_version": current["version"],
        "release_note": release.release_note,
        "target": str(target_path),
        "backup": str(backup),
        "downloaded": downloaded,
    }
