"""macOS、Linux 与 Windows MAA 下载/更新支持。

运行库使用官方 macOS runtime 包；Python API 则通过 HTTP Range 读取 Windows
arm64 ZIP 的中央目录，只提取其中的 ``Python`` 目录，避免下载完整 Windows 包。
Linux 按当前架构下载单个官方 ``tar.gz`` 完整包。
Windows 未安装 Maa 时按当前架构下载完整包，已有安装则提示用户打开 Maa 手动更新。
"""

from __future__ import annotations

import ctypes
import gc
import hashlib
import importlib
import io
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile, ZipInfo

import requests
from packaging.version import InvalidVersion, Version

from arknights_mower.utils.zip_safe import is_unsafe_zip_member

MAA_REPOSITORY = "MaaAssistantArknights/MaaAssistantArknights"
LATEST_RELEASE_API = f"https://api.github.com/repos/{MAA_REPOSITORY}/releases/latest"
MAA_VERSION_API_URLS = (
    "https://api.maa.plus/MaaAssistantArknights/api/version/{channel}.json",
    "https://api2.maa.plus/MaaAssistantArknights/api/version/{channel}.json",
)
MIRRORCHYAN_RELEASE_API = "https://mirrorchyan.com/api/resources/MAA/latest"
REQUEST_TIMEOUT = (10, 60)
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
RANGE_CACHE_SIZE = 256 * 1024
PRESERVED_USER_ENTRIES = ("cache", "config", "config.json")
MAA_CORE_LIBRARY_NAMES = (
    "libMaaCore.dylib",
    "MaaCore.dll",
    "libMaaCore.so",
)

ProgressCallback = Callable[[str, int, int, str], None]


class MaaUpdateError(RuntimeError):
    """MAA 下载或更新流程中的可展示错误。"""


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    size: int
    sha256: str = ""


@dataclass(frozen=True)
class MaaRelease:
    tag: str
    runtime: ReleaseAsset
    python_source: ReleaseAsset | None = None
    source: str = "github"
    channel: str = "stable"

    def as_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "source": self.source,
            "channel": self.channel,
            "runtime": {
                "name": self.runtime.name,
                "size": self.runtime.size,
            },
            "python_source": (
                {
                    "name": self.python_source.name,
                    "size": self.python_source.size,
                }
                if self.python_source is not None
                else None
            ),
        }


@dataclass(frozen=True)
class MirrorChyanCdkStatus:
    valid: bool
    expired: bool
    code: int
    expires_at: int
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "expired": self.expired,
            "code": self.code,
            "expires_at": self.expires_at,
            "message": self.message,
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


def _asset_from_payload(payload: dict[str, Any]) -> ReleaseAsset:
    name = payload.get("name")
    url = payload.get("browser_download_url")
    size = payload.get("size")
    if not isinstance(name, str) or not isinstance(url, str):
        raise MaaUpdateError("MAA Release 资源信息不完整")
    return ReleaseAsset(name=name, url=url, size=int(size or 0))


def normalize_linux_arch(machine: str | None = None) -> str:
    """把 ``platform.machine()`` 转换为 MAA Linux 资源使用的架构名。"""
    machine_name = (machine or platform.machine()).strip().lower().replace("-", "_")
    aliases = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "aarch64": "aarch64",
        "arm64": "aarch64",
    }
    try:
        return aliases[machine_name]
    except KeyError:
        raise MaaUpdateError(
            f"MAA 暂不支持当前 Linux 架构：{machine_name or '未知'}"
        ) from None


def normalize_windows_arch(machine: str | None = None) -> str:
    """把 ``platform.machine()`` 转换为 MAA Windows 资源使用的架构名。"""
    machine_name = (machine or platform.machine()).strip().lower().replace("-", "_")
    aliases = {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    try:
        return aliases[machine_name]
    except KeyError:
        raise MaaUpdateError(
            f"MAA 暂不支持当前 Windows 架构：{machine_name or '未知'}"
        ) from None


def normalize_update_channel(channel: str | None = None) -> str:
    """把用户选择转换为 MAA / Mirror酱使用的版本通道。"""
    normalized = str(channel or "stable").strip().lower()
    if normalized not in {"stable", "beta"}:
        raise MaaUpdateError(f"未知的 MAA 版本通道：{normalized or '未知'}")
    return normalized


def is_maa_version_newer(latest: str, installed: str) -> bool:
    """按 MAA 使用的 SemVer 版本号判断是否存在更新。"""
    try:
        return Version(latest.strip()) > Version(installed.strip())
    except (AttributeError, InvalidVersion):
        raise MaaUpdateError("Maa 版本号格式无效，请检查安装目录") from None


def parse_release(
    payload: dict[str, Any],
    system: str = "darwin",
    machine: str | None = None,
    channel: str = "stable",
) -> MaaRelease:
    """从 GitHub Release JSON 中选择当前系统需要的安装包。"""
    tag = payload.get("tag_name")
    assets = payload.get("assets")
    if not isinstance(tag, str) or not tag.strip():
        raise MaaUpdateError("MAA 最新 Release 缺少版本号")
    if not isinstance(assets, list):
        raise MaaUpdateError("MAA 最新 Release 缺少资源列表")

    system = system.lower()
    channel = normalize_update_channel(channel)
    if system == "darwin":
        expected_runtime = f"MAA-{tag.strip()}-macos-runtime-universal.zip"
        expected_python = f"MAA-{tag.strip()}-win-arm64.zip"
    elif system == "linux":
        arch = normalize_linux_arch(machine)
        expected_runtime = f"MAA-{tag.strip()}-linux-{arch}.tar.gz"
        expected_python = None
    elif system == "windows":
        arch = normalize_windows_arch(machine)
        expected_runtime = f"MAA-{tag.strip()}-win-{arch}.zip"
        expected_python = None
    else:
        raise MaaUpdateError("当前系统不使用 Mower 的 MAA 下载流程")

    runtime_payload = None
    python_payload = None
    for item in assets:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        name = item["name"]
        if name == expected_runtime:
            runtime_payload = item
        elif expected_python is not None and name == expected_python:
            python_payload = item

    if runtime_payload is None:
        if system == "linux":
            raise MaaUpdateError(f"MAA 最新 Release 中没有 Linux {arch} 完整包")
        if system == "windows":
            raise MaaUpdateError(f"MAA 最新 Release 中没有 Windows {arch} 完整包")
        raise MaaUpdateError("MAA 最新 Release 中没有 macOS universal runtime 包")
    if expected_python is not None and python_payload is None:
        raise MaaUpdateError("MAA 最新 Release 中没有 Windows arm64 包")
    return MaaRelease(
        tag=tag.strip(),
        runtime=_asset_from_payload(runtime_payload),
        python_source=(
            _asset_from_payload(python_payload) if python_payload is not None else None
        ),
        channel=channel,
    )


def get_latest_release(
    session: requests.Session | None = None,
    system: str = "darwin",
    machine: str | None = None,
    channel: str = "stable",
) -> MaaRelease:
    """按 MAA 正式版 / 公测版通道读取 GitHub Release 信息。"""
    client = session or requests.Session()
    channel = normalize_update_channel(channel)
    for url_template in MAA_VERSION_API_URLS:
        try:
            response = client.get(
                url_template.format(channel=channel),
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        version = payload.get("version")
        details = payload.get("details")
        if not isinstance(version, str) or not isinstance(details, dict):
            continue
        release_payload = dict(details)
        release_payload.setdefault("tag_name", version)
        if release_payload.get("tag_name") != version:
            continue
        return parse_release(
            release_payload,
            system=system,
            machine=machine,
            channel=channel,
        )

    if channel == "stable":
        try:
            response = client.get(
                LATEST_RELEASE_API,
                headers={"Accept": "application/vnd.github+json"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as e:
            raise MaaUpdateError(f"获取 MAA 正式版本失败：{e}") from e
        if isinstance(payload, dict):
            return parse_release(
                payload,
                system=system,
                machine=machine,
                channel=channel,
            )
    channel_label = "公测版" if channel == "beta" else "正式版"
    raise MaaUpdateError(f"获取 MAA {channel_label}失败")


_MIRRORCHYAN_ERRORS = {
    1001: "Mirror酱请求参数错误",
    7001: "Mirror酱 CDK 已过期，请使用新的 CDK。",
    7002: "Mirror酱 CDK 无效，请检查输入是否正确。",
    7003: "Mirror酱 CDK 今日下载次数已达上限。",
    7004: "Mirror酱 CDK 与 MAA 资源不匹配。",
    7005: "Mirror酱 CDK 已失效（已被封禁）。",
    8001: "Mirror酱中没有对应平台的 MAA 资源",
    8002: "Mirror酱不支持请求的系统",
    8003: "Mirror酱不支持请求的架构",
    8004: "Mirror酱不支持请求的更新通道",
}


def mirrorchyan_sp_id() -> str:
    """生成只用于 Mirror酱设备区分的稳定散列，不发送原始机器信息。"""
    identity = f"arknights-mower:{platform.node()}:{uuid.getnode()}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def _request_mirrorchyan(
    token: str,
    os_name: str,
    arch: str,
    channel: str,
    session: requests.Session,
    sp_id: str,
) -> tuple[int, dict[str, Any]]:
    params = {
        "cdk": token,
        "user_agent": "arknights_mower",
        "os": os_name,
        "arch": arch,
        "channel": channel,
        "sp_id": sp_id,
    }
    try:
        response = session.get(
            MIRRORCHYAN_RELEASE_API,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        # requests 的异常字符串可能包含带 cdk 的完整查询 URL，避免向日志传递。
        raise MaaUpdateError("连接 Mirror酱服务失败") from None
    if not isinstance(payload, dict):
        raise MaaUpdateError("Mirror酱返回了无效数据")
    try:
        code = int(payload.get("code"))
    except (TypeError, ValueError):
        raise MaaUpdateError("Mirror酱返回了无效状态码") from None
    data = payload.get("data")
    return code, data if isinstance(data, dict) else {}


def _mirrorchyan_expired_time(data: dict[str, Any]) -> int:
    value = data.get("cdk_expired_time")
    if isinstance(value, bool):
        return 0
    try:
        expires_at = int(value)
    except (TypeError, ValueError):
        return 0
    return max(expires_at, 0)


def get_mirrorchyan_cdk_status(
    token: str,
    session: requests.Session | None = None,
    system: str = "darwin",
    machine: str | None = None,
    channel: str = "stable",
    now: float | None = None,
) -> MirrorChyanCdkStatus:
    """查询 Mirror酱 CDK 状态及有效期，不在错误中回显 CDK。"""
    token = token.strip()
    if not token:
        return MirrorChyanCdkStatus(
            valid=False,
            expired=False,
            code=7002,
            expires_at=0,
            message=_MIRRORCHYAN_ERRORS[7002],
        )

    system = system.lower()
    channel = normalize_update_channel(channel)
    if system == "darwin":
        os_name, arch = "macos", "arm64"
    elif system == "linux":
        os_name, arch = "linux", normalize_linux_arch(machine)
    elif system == "windows":
        os_name, arch = "win", normalize_windows_arch(machine)
    else:
        raise MaaUpdateError("当前系统不使用 Mower 的 MAA 下载流程")

    client = session or requests.Session()
    code, data = _request_mirrorchyan(
        token,
        os_name,
        arch,
        channel,
        client,
        mirrorchyan_sp_id(),
    )
    expires_at = _mirrorchyan_expired_time(data)
    expired = code == 7001 or (
        expires_at > 0 and expires_at <= int(time.time() if now is None else now)
    )
    if expired:
        return MirrorChyanCdkStatus(
            valid=False,
            expired=True,
            code=7001 if code == 0 else code,
            expires_at=expires_at,
            message=_MIRRORCHYAN_ERRORS[7001],
        )
    if code != 0:
        return MirrorChyanCdkStatus(
            valid=False,
            expired=False,
            code=code,
            expires_at=expires_at,
            message=_MIRRORCHYAN_ERRORS.get(code, "Mirror酱服务返回业务错误"),
        )
    return MirrorChyanCdkStatus(
        valid=True,
        expired=False,
        code=0,
        expires_at=expires_at,
        message="Mirror酱 CDK 有效",
    )


def _get_mirrorchyan_asset(
    token: str,
    os_name: str,
    arch: str,
    channel: str,
    session: requests.Session,
    sp_id: str,
) -> tuple[str, ReleaseAsset]:
    code, data = _request_mirrorchyan(
        token,
        os_name,
        arch,
        channel,
        session,
        sp_id,
    )
    if code != 0:
        raise MaaUpdateError(_MIRRORCHYAN_ERRORS.get(code, "Mirror酱服务返回业务错误"))
    expires_at = _mirrorchyan_expired_time(data)
    if expires_at and expires_at <= int(time.time()):
        raise MaaUpdateError(_MIRRORCHYAN_ERRORS[7001])
    if not data:
        raise MaaUpdateError("Mirror酱返回的 MAA 资源信息不完整")

    version = data.get("version_name")
    url = data.get("url")
    size = data.get("filesize")
    checksum = data.get("sha256")
    if not isinstance(version, str) or not isinstance(url, str):
        raise MaaUpdateError("Mirror酱返回的 MAA 下载信息不完整")
    if data.get("update_type") != "full":
        raise MaaUpdateError("Mirror酱未返回 MAA 完整包")
    if urlsplit(url).scheme != "https":
        raise MaaUpdateError("Mirror酱返回了无效的 MAA 下载地址")

    platform_label = f"{os_name}-{arch}"
    suffix = ".tar.gz" if os_name == "linux" else ".zip"
    return version, ReleaseAsset(
        name=f"MAA-{version}-{platform_label}{suffix}",
        url=url,
        size=int(size or 0),
        sha256=checksum if isinstance(checksum, str) else "",
    )


def get_mirrorchyan_release(
    token: str,
    session: requests.Session | None = None,
    system: str = "darwin",
    machine: str | None = None,
    channel: str = "stable",
) -> MaaRelease:
    """通过 Mirror酱取得当前系统所需的 MAA 完整包。"""
    token = token.strip()
    if not token:
        raise MaaUpdateError("请填写 Mirror酱 CDK")
    client = session or requests.Session()
    sp_id = mirrorchyan_sp_id()
    system = system.lower()
    channel = normalize_update_channel(channel)
    if system in {"linux", "windows"}:
        if system == "linux":
            os_name = "linux"
            arch = normalize_linux_arch(machine)
        else:
            os_name = "win"
            arch = normalize_windows_arch(machine)
        version, asset = _get_mirrorchyan_asset(
            token,
            os_name,
            arch,
            channel,
            client,
            sp_id,
        )
        return MaaRelease(
            tag=version,
            runtime=asset,
            source="mirrorchyan",
            channel=channel,
        )
    if system != "darwin":
        raise MaaUpdateError("当前系统不使用 Mower 的 MAA 下载流程")

    mac_version, mac_asset = _get_mirrorchyan_asset(
        token,
        "macos",
        "arm64",
        channel,
        client,
        sp_id,
    )
    win_version, win_asset = _get_mirrorchyan_asset(
        token,
        "win",
        "arm64",
        channel,
        client,
        sp_id,
    )
    if mac_version != win_version:
        raise MaaUpdateError("Mirror酱的 macOS 与 Windows MAA 版本不一致")
    return MaaRelease(
        tag=mac_version,
        runtime=mac_asset,
        python_source=win_asset,
        source="mirrorchyan",
        channel=channel,
    )


class HTTPRangeReader(io.RawIOBase):
    """将支持 Range 的 HTTP 资源包装成 ZipFile 可用的只读 seek 流。"""

    def __init__(
        self,
        url: str,
        session: requests.Session | None = None,
        progress: Callable[[int], None] | None = None,
        cache_size: int = RANGE_CACHE_SIZE,
    ) -> None:
        super().__init__()
        self._session = session or requests.Session()
        self._progress = progress
        self._cache_size = cache_size
        self._position = 0
        self._cache_start = 0
        self._cache = b""
        try:
            response = self._session.head(
                url,
                allow_redirects=True,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise MaaUpdateError(f"读取 MAA Python 包信息失败：{e}") from e
        try:
            try:
                self._length = int(response.headers["Content-Length"])
            except (KeyError, TypeError, ValueError) as e:
                raise MaaUpdateError("MAA Python 包没有提供文件大小") from e
            self._url = response.url
        finally:
            response.close()

    @property
    def length(self) -> int:
        return self._length

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._position

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if whence == os.SEEK_SET:
            position = offset
        elif whence == os.SEEK_CUR:
            position = self._position + offset
        elif whence == os.SEEK_END:
            position = self._length + offset
        else:
            raise ValueError(f"无效的 seek whence：{whence}")
        if position < 0:
            raise ValueError("seek 位置不能为负数")
        self._position = position
        return position

    def _cache_contains(self, start: int, end: int) -> bool:
        cache_end = self._cache_start + len(self._cache)
        return bool(self._cache) and self._cache_start <= start and end <= cache_end

    def _fetch(self, start: int, end: int) -> bytes:
        try:
            response = self._session.get(
                self._url,
                headers={"Range": f"bytes={start}-{end - 1}"},
                stream=True,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as e:
            raise MaaUpdateError(f"按需下载 MAA Python 文件失败：{e}") from e
        try:
            if response.status_code != 206:
                raise MaaUpdateError(
                    "MAA 下载服务器未响应 Range 请求，已停止以避免下载完整 Windows 包"
                )
            content_range = response.headers.get("Content-Range", "")
            expected_prefix = f"bytes {start}-{end - 1}/"
            if not content_range.startswith(expected_prefix):
                raise MaaUpdateError("MAA 下载服务器返回了错误的 Range 数据")
            data = response.content
        finally:
            response.close()
        if len(data) != end - start:
            raise MaaUpdateError("MAA Python 包分段下载不完整")
        if self._progress is not None:
            self._progress(len(data))
        return data

    def read(self, size: int = -1) -> bytes:
        if self._position >= self._length or size == 0:
            return b""
        if size is None or size < 0:
            size = self._length - self._position
        end = min(self._length, self._position + size)
        start = self._position

        if self._cache_contains(start, end):
            offset = start - self._cache_start
            data = self._cache[offset : offset + (end - start)]
        else:
            block_start = start // self._cache_size * self._cache_size
            block_end = min(self._length, block_start + self._cache_size)
            if end <= block_end and end - start <= self._cache_size:
                self._cache_start = block_start
                self._cache = self._fetch(block_start, block_end)
                offset = start - block_start
                data = self._cache[offset : offset + (end - start)]
            else:
                data = self._fetch(start, end)
                self._cache = b""
        self._position += len(data)
        return data


def _safe_parts(info: ZipInfo) -> tuple[str, ...]:
    if is_unsafe_zip_member(info.filename) or "\\" in info.filename:
        raise MaaUpdateError(f"MAA 压缩包包含非法路径：{info.filename}")
    return PurePosixPath(info.filename).parts


def _prepare_output_path(destination: Path, parts: tuple[str, ...]) -> Path:
    output = destination.joinpath(*parts)
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _extract_member(archive: ZipFile, info: ZipInfo, output: Path) -> None:
    mode = info.external_attr >> 16
    if info.is_dir():
        output.mkdir(parents=True, exist_ok=True)
        return
    if stat.S_ISLNK(mode):
        link_target = archive.read(info).decode("utf-8")
        link_path = PurePosixPath(link_target)
        if link_path.is_absolute() or ".." in link_path.parts:
            raise MaaUpdateError(f"MAA 压缩包包含非法符号链接：{info.filename}")
        if output.exists() or output.is_symlink():
            output.unlink()
        output.symlink_to(link_target)
        return
    with archive.open(info) as source, output.open("wb") as target:
        shutil.copyfileobj(source, target, DOWNLOAD_CHUNK_SIZE)
    permissions = mode & 0o777
    if permissions:
        output.chmod(permissions)


def extract_runtime(
    archive_path: Path,
    destination: Path,
    callback: ProgressCallback | None = None,
) -> None:
    """解压 runtime 包，并去掉官方 ZIP 的版本根目录。"""
    try:
        with ZipFile(archive_path) as archive:
            infos = archive.infolist()
            file_infos = [info for info in infos if not info.is_dir()]
            if not file_infos:
                raise MaaUpdateError("MAA macOS runtime 包为空")
            roots = {_safe_parts(info)[0] for info in file_infos}
            if len(roots) != 1:
                raise MaaUpdateError("MAA macOS runtime 包目录结构异常")
            root = roots.pop()
            total = sum(info.file_size for info in file_infos)
            current = 0
            for index, info in enumerate(infos):
                parts = _safe_parts(info)
                if not parts or parts[0] != root:
                    raise MaaUpdateError("MAA macOS runtime 包目录结构异常")
                relative_parts = parts[1:]
                if not relative_parts:
                    continue
                output = _prepare_output_path(destination, relative_parts)
                _extract_member(archive, info, output)
                if not info.is_dir():
                    current += info.file_size
                if index % 100 == 0 or index == len(infos) - 1:
                    _emit(
                        callback,
                        "extracting_runtime",
                        current,
                        total,
                        "正在解压 macOS 运行库",
                    )
    except BadZipFile as e:
        raise MaaUpdateError("MAA macOS runtime 下载包已损坏") from e


def extract_windows_package(
    archive_path: Path,
    destination: Path,
    callback: ProgressCallback | None = None,
) -> None:
    """安全解压 Windows 完整包，兼容根目录或单层版本目录结构。"""
    try:
        with ZipFile(archive_path) as archive:
            infos = archive.infolist()
            file_infos = [info for info in infos if not info.is_dir()]
            if not file_infos:
                raise MaaUpdateError("MAA Windows 完整包为空")
            file_parts = [_safe_parts(info) for info in file_infos]
            roots = {parts[0] for parts in file_parts}
            strip_root = len(roots) == 1 and all(len(parts) > 1 for parts in file_parts)
            entries: list[tuple[ZipInfo, tuple[str, ...]]] = []
            seen: set[tuple[str, ...]] = set()
            for info in infos:
                parts = _safe_parts(info)
                relative_parts = parts[1:] if strip_root and parts else parts
                if not relative_parts:
                    continue
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise MaaUpdateError(
                        f"MAA Windows 完整包包含符号链接：{info.filename}"
                    )
                if not info.is_dir():
                    if relative_parts in seen:
                        raise MaaUpdateError(
                            f"MAA Windows 完整包包含重复路径：{info.filename}"
                        )
                    seen.add(relative_parts)
                entries.append((info, relative_parts))

            total = sum(info.file_size for info in file_infos)
            current = 0
            for info, parts in entries:
                output = _prepare_output_path(destination, parts)
                _extract_member(archive, info, output)
                if not info.is_dir():
                    current += info.file_size
                _emit(
                    callback,
                    "extracting_windows",
                    current,
                    total,
                    "正在解压 Windows MAA 完整包",
                )
    except BadZipFile as e:
        raise MaaUpdateError("MAA Windows 完整包已损坏") from e
    except OSError as e:
        raise MaaUpdateError(f"MAA Windows 完整包解压失败：{e}") from e

    required = (
        destination / "MaaCore.dll",
        destination / "MAA.exe",
        destination / "MAA.Updater.exe",
        destination / "resource",
        destination / "Python",
    )
    if not all(path.is_file() for path in required[:3]) or not all(
        path.is_dir() for path in required[3:]
    ):
        raise MaaUpdateError(
            "MAA Windows 完整包缺少 MaaCore、MAA.exe、更新程序、resource 或 Python"
        )


def _safe_tar_parts(name: str) -> tuple[str, ...]:
    if not name or "\\" in name:
        raise MaaUpdateError(f"MAA Linux 包包含非法路径：{name}")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise MaaUpdateError(f"MAA Linux 包包含非法路径：{name}")
    return tuple(part for part in path.parts if part not in {"", "."})


def _linux_tar_entries(
    archive: tarfile.TarFile,
) -> list[tuple[tarfile.TarInfo, tuple[str, ...]]]:
    raw_entries = [
        (member, _safe_tar_parts(member.name)) for member in archive.getmembers()
    ]
    file_parts = [
        parts for member, parts in raw_entries if not member.isdir() and parts
    ]
    if not file_parts:
        raise MaaUpdateError("MAA Linux 完整包为空")

    roots = {parts[0] for parts in file_parts}
    strip_root = len(roots) == 1 and all(len(parts) > 1 for parts in file_parts)
    entries: list[tuple[tarfile.TarInfo, tuple[str, ...]]] = []
    seen: set[tuple[str, ...]] = set()
    symlink_paths: set[tuple[str, ...]] = set()
    for member, parts in raw_entries:
        relative_parts = parts[1:] if strip_root and parts else parts
        if not relative_parts:
            continue
        if relative_parts in seen:
            raise MaaUpdateError(f"MAA Linux 包包含重复路径：{member.name}")
        seen.add(relative_parts)
        if member.issym():
            link_parts = _safe_tar_parts(member.linkname)
            if not link_parts or PurePosixPath(member.linkname).is_absolute():
                raise MaaUpdateError(f"MAA Linux 包包含非法符号链接：{member.name}")
            symlink_paths.add(relative_parts)
        elif member.islnk() or not (member.isdir() or member.isfile()):
            raise MaaUpdateError(f"MAA Linux 包包含不支持的文件类型：{member.name}")
        entries.append((member, relative_parts))

    for parts in seen:
        if any(parts[: len(link)] == link for link in symlink_paths if parts != link):
            raise MaaUpdateError("MAA Linux 包包含指向子路径的符号链接")
    return entries


def extract_linux_package(
    archive_path: Path,
    destination: Path,
    callback: ProgressCallback | None = None,
) -> None:
    """安全解压 Linux ``tar.gz`` 完整包，并兼容可选的单层版本根目录。"""
    try:
        with tarfile.open(archive_path, mode="r:*") as archive:
            entries = _linux_tar_entries(archive)
            total = sum(member.size for member, _ in entries if member.isfile())
            current = 0
            for member, parts in entries:
                if member.issym():
                    continue
                output = _prepare_output_path(destination, parts)
                if member.isdir():
                    output.mkdir(parents=True, exist_ok=True)
                    output.chmod(member.mode & 0o777)
                    continue
                source = archive.extractfile(member)
                if source is None:
                    raise MaaUpdateError(f"MAA Linux 包中的文件读取失败：{member.name}")
                with source, output.open("wb") as target:
                    shutil.copyfileobj(source, target, DOWNLOAD_CHUNK_SIZE)
                output.chmod(member.mode & 0o777)
                current += member.size
                _emit(
                    callback,
                    "extracting_linux",
                    current,
                    total,
                    "正在解压 Linux MAA 完整包",
                )

            for member, parts in entries:
                if not member.issym():
                    continue
                output = _prepare_output_path(destination, parts)
                if output.exists() or output.is_symlink():
                    _remove_path(output)
                output.symlink_to(member.linkname)
    except (tarfile.TarError, OSError) as e:
        raise MaaUpdateError(f"MAA Linux 完整包解压失败：{e}") from e

    required = (
        destination / "libMaaCore.so",
        destination / "resource",
        destination / "Python",
    )
    if not required[0].is_file() or not all(path.is_dir() for path in required[1:]):
        raise MaaUpdateError("MAA Linux 完整包缺少 MaaCore、resource 或 Python")


def _extract_python_from_zip(
    archive: ZipFile,
    destination: Path,
    callback: ProgressCallback | None,
) -> None:
    selected: list[tuple[ZipInfo, tuple[str, ...]]] = []
    for info in archive.infolist():
        parts = _safe_parts(info)
        if parts and parts[0] == "Python":
            selected.append((info, parts))
    if not selected:
        raise MaaUpdateError("MAA Windows arm64 包中没有 Python 文件夹")
    total = sum(info.file_size for info, _ in selected if not info.is_dir())
    current = 0
    for info, parts in selected:
        output = _prepare_output_path(destination, parts)
        _extract_member(archive, info, output)
        if not info.is_dir():
            current += info.file_size
        _emit(
            callback,
            "extracting_python",
            current,
            total,
            "正在准备 Python API 文件",
        )


def extract_python_folder(
    asset: ReleaseAsset,
    destination: Path,
    session: requests.Session | None = None,
    callback: ProgressCallback | None = None,
) -> int:
    """按需读取远程 ZIP，只下载并解压根目录下的 Python 文件夹。"""
    downloaded = 0

    def on_range(size: int) -> None:
        nonlocal downloaded
        downloaded += size
        _emit(
            callback,
            "downloading_python",
            downloaded,
            0,
            "正在按需读取 Windows 包中的 Python 文件夹",
        )

    reader = HTTPRangeReader(asset.url, session=session, progress=on_range)
    try:
        with ZipFile(reader) as archive:
            _extract_python_from_zip(archive, destination, callback)
    except BadZipFile as e:
        raise MaaUpdateError("MAA Windows arm64 包目录读取失败") from e
    finally:
        reader.close()
    return downloaded


def extract_python_archive(
    archive_path: Path,
    destination: Path,
    callback: ProgressCallback | None = None,
) -> None:
    """从已经完整下载的 Windows arm64 包中提取 Python 文件夹。"""
    try:
        with ZipFile(archive_path) as archive:
            _extract_python_from_zip(archive, destination, callback)
    except BadZipFile as e:
        raise MaaUpdateError("MAA Windows arm64 下载包已损坏") from e


def _extract_dmg(
    archive_path: Path,
    destination: Path,
    callback: ProgressCallback | None,
) -> None:
    try:
        with ZipFile(archive_path) as archive:
            dmg_infos = [
                info
                for info in archive.infolist()
                if not info.is_dir()
                and _safe_parts(info)
                and info.filename.lower().endswith(".dmg")
            ]
            if len(dmg_infos) != 1:
                raise MaaUpdateError("Mirror酱 macOS 包中没有唯一的 DMG 文件")
            info = dmg_infos[0]
            current = 0
            with archive.open(info) as source, destination.open("wb") as target:
                while chunk := source.read(DOWNLOAD_CHUNK_SIZE):
                    target.write(chunk)
                    current += len(chunk)
                    _emit(
                        callback,
                        "extracting_mirror_dmg",
                        current,
                        info.file_size,
                        "正在从 Mirror酱包中提取 DMG",
                    )
    except BadZipFile as e:
        raise MaaUpdateError("Mirror酱 macOS 下载包已损坏") from e


def _copy_tree_with_progress(
    source: Path,
    destination: Path,
    callback: ProgressCallback | None,
) -> None:
    items = list(source.rglob("*"))
    total = sum(
        item.stat().st_size
        for item in items
        if not item.is_symlink() and item.is_file()
    )
    current = 0
    destination.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(items):
        relative = item.relative_to(source)
        output = destination / relative
        if item.is_symlink():
            output.parent.mkdir(parents=True, exist_ok=True)
            output.symlink_to(os.readlink(item))
        elif item.is_dir():
            output.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, output)
            current += item.stat().st_size
        if index % 100 == 0 or index == len(items) - 1:
            _emit(
                callback,
                "extracting_mirror_runtime",
                current,
                total,
                "正在从 MAA.app 分离运行库与资源",
            )


def _create_runtime_library_aliases(destination: Path) -> None:
    aliases = {
        "libopencv_world4.dylib": "libopencv_world4.*.dylib",
        "libonnxruntime.dylib": "libonnxruntime.*.dylib",
    }
    for alias, pattern in aliases.items():
        alias_path = destination / alias
        if alias_path.exists() or alias_path.is_symlink():
            continue
        candidates = sorted(
            path for path in destination.glob(pattern) if path.name != alias
        )
        if candidates:
            alias_path.symlink_to(candidates[-1].name)


def extract_mirror_macos_package(
    archive_path: Path,
    destination: Path,
    work_dir: Path,
    callback: ProgressCallback | None = None,
) -> None:
    """从 Mirror酱的 macOS GUI ZIP/DMG 中分离 MaaCore 运行库和 resource。"""
    dmg_path = work_dir / "MAA-macos.dmg"
    mount_point = work_dir / "dmg-mount"
    _extract_dmg(archive_path, dmg_path, callback)
    mount_point.mkdir()
    attached = False
    try:
        try:
            subprocess.run(
                [
                    "/usr/bin/hdiutil",
                    "attach",
                    "-readonly",
                    "-nobrowse",
                    "-mountpoint",
                    str(mount_point),
                    str(dmg_path),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
            attached = True
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            raise MaaUpdateError("挂载 Mirror酱 MAA DMG 失败") from None

        apps = sorted(mount_point.glob("*.app"))
        if len(apps) != 1:
            raise MaaUpdateError("Mirror酱 MAA DMG 中没有唯一的 .app")
        contents = apps[0] / "Contents"
        resource = contents / "Resources" / "resource"
        frameworks = contents / "Frameworks"
        if not resource.is_dir() or not frameworks.is_dir():
            raise MaaUpdateError("Mirror酱 MAA.app 缺少运行资源")

        _copy_tree_with_progress(resource, destination / "resource", callback)
        dylibs = sorted(frameworks.glob("*.dylib"))
        if not dylibs:
            raise MaaUpdateError("Mirror酱 MAA.app 缺少 MaaCore 动态库")
        for dylib in dylibs:
            shutil.copy2(dylib, destination / dylib.name)
        _create_runtime_library_aliases(destination)

        if not (destination / "libMaaCore.dylib").is_file():
            raise MaaUpdateError("Mirror酱 MAA.app 中没有 libMaaCore.dylib")
    finally:
        if attached:
            try:
                subprocess.run(
                    ["/usr/bin/hdiutil", "detach", str(mount_point)],
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                try:
                    subprocess.run(
                        ["/usr/bin/hdiutil", "detach", "-force", str(mount_point)],
                        check=False,
                        capture_output=True,
                        timeout=60,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    pass


def download_asset(
    asset: ReleaseAsset,
    destination: Path,
    session: requests.Session | None = None,
    callback: ProgressCallback | None = None,
    phase: str = "downloading_runtime",
    message: str = "正在下载 macOS 运行库",
) -> int:
    """流式下载一个完整 Release asset。"""
    client = session or requests.Session()
    part_path = destination.with_suffix(destination.suffix + ".part")
    downloaded = 0
    digest = hashlib.sha256()
    try:
        with client.get(
            asset.url,
            stream=True,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length") or asset.size or 0)
            with part_path.open("wb") as target:
                for chunk in response.iter_content(DOWNLOAD_CHUNK_SIZE):
                    if not chunk:
                        continue
                    target.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    _emit(
                        callback,
                        phase,
                        downloaded,
                        total,
                        message,
                    )
    except requests.RequestException as e:
        raise MaaUpdateError(f"下载 MAA 包失败：{e}") from e
    finally:
        if part_path.exists() and downloaded == 0:
            part_path.unlink()
    if asset.size and downloaded != asset.size:
        part_path.unlink(missing_ok=True)
        raise MaaUpdateError(f"MAA 下载包不完整：{downloaded}/{asset.size} 字节")
    if asset.sha256 and digest.hexdigest().lower() != asset.sha256.lower():
        part_path.unlink(missing_ok=True)
        raise MaaUpdateError("MAA 下载包 SHA-256 校验失败")
    os.replace(part_path, destination)
    return downloaded


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def preserve_user_data(
    current_install: Path,
    staged_install: Path,
    callback: ProgressCallback | None = None,
) -> list[str]:
    """把旧目录中的缓存/配置复制到新目录，程序文件仍全部使用新版本。"""
    preserved = []
    for name in PRESERVED_USER_ENTRIES:
        source = current_install / name
        if not source.exists() and not source.is_symlink():
            continue
        destination = staged_install / name
        if source.is_symlink():
            if destination.exists() or destination.is_symlink():
                _remove_path(destination)
            destination.symlink_to(os.readlink(source))
        elif source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        preserved.append(name)
        _emit(
            callback,
            "preserving_user_data",
            len(preserved),
            len(PRESERVED_USER_ENTRIES),
            "正在保留 MAA 缓存与配置",
        )
    return preserved


def backup_path_for(target: Path | str) -> Path:
    path = Path(target).expanduser()
    return path.with_name(path.name + ".old")


def replace_with_backup(staged: Path, target: Path, work_dir: Path) -> Path:
    """以 ``target.old`` 保存原版本，再原子换入已完成的 staging 目录。

    上一次的 ``.old`` 会先移入本次临时目录；成功后随临时目录清理，失败时恢复。
    """
    backup = backup_path_for(target)
    previous_backup = work_dir / "previous.old"
    had_previous_backup = backup.exists() or backup.is_symlink()
    target_moved = False

    try:
        if had_previous_backup:
            os.replace(backup, previous_backup)
        if target.exists() or target.is_symlink():
            os.replace(target, backup)
            target_moved = True
        os.replace(staged, target)
    except Exception:
        if target_moved and not target.exists() and backup.exists():
            os.replace(backup, target)
        if had_previous_backup and previous_backup.exists():
            if backup.exists() or backup.is_symlink():
                _remove_path(backup)
            os.replace(previous_backup, backup)
        raise
    return backup


def _find_maa_core_library(target: Path | str) -> Path | None:
    path = Path(target).expanduser()
    if path.is_file():
        if path.name in MAA_CORE_LIBRARY_NAMES:
            return path
        path = path.parent
    if not path.is_dir():
        return None
    for name in MAA_CORE_LIBRARY_NAMES:
        candidate = path / name
        if candidate.is_file():
            return candidate
    return None


def has_maa_installation(target: Path | str) -> bool:
    """根据 Maa 核心或 Windows 入口文件判断目录内是否已有 Maa。"""
    path = Path(target).expanduser()
    known_names = {
        name.lower() for name in (*MAA_CORE_LIBRARY_NAMES, "MAA.exe", "MAA.Updater.exe")
    }
    if path.is_file():
        return path.name.lower() in known_names
    if not path.is_dir():
        return False
    return any(
        child.is_file() and child.name.lower() in known_names
        for child in path.iterdir()
    )


def _close_dynamic_library(handle: int) -> None:
    try:
        import _ctypes

        close = getattr(
            _ctypes,
            "FreeLibrary" if os.name == "nt" else "dlclose",
            None,
        )
        if close is not None:
            close(handle)
    except (ImportError, OSError):
        pass


def read_installed_version(target: Path | str) -> str:
    """直接调用安装目录中 MaaCore 的版本接口，不依赖更新记录文件。"""
    library_path = _find_maa_core_library(target)
    if library_path is None:
        return ""

    library = None
    get_version = None
    try:
        library = ctypes.CDLL(str(library_path))
        get_version = library.AsstGetVersion
        get_version.argtypes = []
        get_version.restype = ctypes.c_char_p
        raw_version = get_version()
        if not raw_version:
            return ""
        version = raw_version.decode("utf-8").strip()
        if not version or len(version) > 128 or any(ord(char) < 32 for char in version):
            return ""
        return version
    except (AttributeError, OSError, UnicodeDecodeError, ValueError):
        return ""
    finally:
        get_version = None
        if library is not None:
            handle = library._handle
            library = None
            _close_dynamic_library(handle)


def clear_loaded_maa_cache(target: Path | str) -> None:
    """释放 Mower 进程内已经读取的 Maa 实例、模块和导入路径。"""
    main_module = sys.modules.get("arknights_mower.__main__")
    scheduler = getattr(main_module, "base_scheduler", None)
    if scheduler is not None:
        scheduler.MAA = None

    base_schedule_module = sys.modules.get("arknights_mower.solvers.base_schedule")
    if base_schedule_module is not None:
        setattr(base_schedule_module, "Message", None)

    # Asst.load 把 MaaCore 保存在 Asst 的类属性中；仅移除 sys.modules 不会释放
    # 已加载的旧动态库。先销毁实例，再显式关闭句柄，后续版本读取才会加载新文件。
    gc.collect()
    asst_module = sys.modules.get("asst.asst")
    asst_class = getattr(asst_module, "Asst", None)
    library = getattr(asst_class, "_Asst__lib", None)
    handle = getattr(library, "_handle", None)
    if asst_class is not None and library is not None:
        setattr(asst_class, "_Asst__lib", None)
    if isinstance(handle, int) and handle:
        _close_dynamic_library(handle)

    for module_name in list(sys.modules):
        if module_name == "asst" or module_name.startswith("asst."):
            sys.modules.pop(module_name, None)

    python_path = str(Path(target).expanduser() / "Python")
    sys.path[:] = [entry for entry in sys.path if entry != python_path]
    importlib.invalidate_caches()
    gc.collect()


def install_latest_maa(
    target: Path | str,
    callback: ProgressCallback | None = None,
    session: requests.Session | None = None,
    source: str = "github",
    mirror_token: str = "",
    system: str = "darwin",
    machine: str | None = None,
    channel: str = "stable",
) -> dict[str, Any]:
    """下载或更新 MAA，切换成功后把原目录保留为同级 ``.old``。"""
    target_path = Path(target).expanduser()
    if not target_path.name or target_path == target_path.parent:
        raise MaaUpdateError("Maa 目录无效")
    if target_path.exists() and not target_path.is_dir():
        raise MaaUpdateError("Maa 目录指向的不是文件夹")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    system = system.lower()
    channel = normalize_update_channel(channel)
    installed_before = has_maa_installation(target_path)
    operation = "更新" if installed_before else "下载"
    if system not in {"darwin", "linux", "windows"}:
        raise MaaUpdateError("当前系统不使用 Mower 的 MAA 下载流程")
    if system == "linux":
        arch = normalize_linux_arch(machine)
    elif system == "windows":
        arch = normalize_windows_arch(machine)
        if installed_before:
            raise MaaUpdateError("已检测到 Windows Maa，请手动打开 Maa 进行更新")
    else:
        arch = ""
    if source not in {"github", "mirrorchyan"}:
        raise MaaUpdateError(f"未知的 MAA {operation}源")
    channel_label = "公测版" if channel == "beta" else "正式版"
    if source == "mirrorchyan":
        _emit(
            callback,
            "checking",
            0,
            0,
            f"正在通过 Mirror酱获取 MAA {channel_label}{operation}信息",
        )
        release = get_mirrorchyan_release(
            mirror_token,
            client,
            system=system,
            machine=machine,
            channel=channel,
        )
    else:
        _emit(
            callback,
            "checking",
            0,
            0,
            f"正在通过 GitHub 获取 MAA {channel_label}{operation}信息",
        )
        release = get_latest_release(
            client,
            system=system,
            machine=machine,
            channel=channel,
        )

    prefix = f".{target_path.name}.maa-update-"
    with tempfile.TemporaryDirectory(prefix=prefix, dir=target_path.parent) as temp:
        work_dir = Path(temp)
        archive_path = work_dir / release.runtime.name
        staged = work_dir / "new"
        staged.mkdir()

        if system == "linux":
            runtime_downloaded = download_asset(
                release.runtime,
                archive_path,
                session=client,
                callback=callback,
                phase="downloading_linux",
                message=(
                    f"正在通过 Mirror酱为 MAA {operation}下载 Linux {arch} 完整包"
                    if release.source == "mirrorchyan"
                    else f"正在为 MAA {operation}下载 Linux {arch} 完整包"
                ),
            )
            extract_linux_package(archive_path, staged, callback=callback)
            python_downloaded = 0
            python_full_size = 0
        elif system == "windows":
            runtime_downloaded = download_asset(
                release.runtime,
                archive_path,
                session=client,
                callback=callback,
                phase="downloading_windows",
                message=(
                    f"正在通过 Mirror酱下载 Windows {arch} 完整包"
                    if release.source == "mirrorchyan"
                    else f"正在下载 Windows {arch} 完整包"
                ),
            )
            extract_windows_package(archive_path, staged, callback=callback)
            python_downloaded = 0
            python_full_size = 0
        elif release.source == "mirrorchyan":
            runtime_downloaded = download_asset(
                release.runtime,
                archive_path,
                session=client,
                callback=callback,
                phase="downloading_mirror_macos",
                message=f"正在通过 Mirror酱为 MAA {operation}下载 macOS 完整包",
            )
            extract_mirror_macos_package(
                archive_path,
                staged,
                work_dir,
                callback=callback,
            )
            if release.python_source is None:
                raise MaaUpdateError("Mirror酱没有返回 Windows arm64 Python 来源包")
            python_archive = work_dir / release.python_source.name
            python_downloaded = download_asset(
                release.python_source,
                python_archive,
                session=client,
                callback=callback,
                phase="downloading_mirror_python",
                message=(
                    f"正在通过 Mirror酱为 MAA {operation}下载 Windows arm64 Python 来源包"
                ),
            )
            python_full_size = release.python_source.size
            extract_python_archive(python_archive, staged, callback=callback)
        else:
            runtime_downloaded = download_asset(
                release.runtime,
                archive_path,
                session=client,
                callback=callback,
                message=f"正在为 MAA {operation}下载 macOS 运行库",
            )
            extract_runtime(archive_path, staged, callback=callback)
            if release.python_source is None:
                raise MaaUpdateError(
                    "GitHub Release 没有返回 Windows arm64 Python 来源包"
                )
            python_downloaded = extract_python_folder(
                release.python_source,
                staged,
                session=client,
                callback=callback,
            )
            python_full_size = release.python_source.size
        preserved = preserve_user_data(target_path, staged, callback=callback)

        _emit(
            callback,
            "installing",
            0,
            0,
            (
                "正在安装已下载的 Windows Maa 完整包"
                if system == "windows"
                else (
                    "正在备份旧版本并完成 Maa 更新"
                    if installed_before
                    else "正在安装已下载的 Maa"
                )
            ),
        )
        try:
            backup = replace_with_backup(staged, target_path, work_dir)
        except OSError as e:
            raise MaaUpdateError(f"完成 MAA {operation}时替换目录失败：{e}") from e

    return {
        "version": release.tag,
        "source": release.source,
        "channel": release.channel,
        "operation": "update" if installed_before else "download",
        "platform": system,
        "arch": arch,
        "target": str(target_path),
        "backup": str(backup),
        "runtime_downloaded": runtime_downloaded,
        "python_downloaded": python_downloaded,
        "python_full_size": python_full_size,
        "preserved": preserved,
    }
