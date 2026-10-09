"""共享持久资源包：不可变版本目录、整包选择和任务边界缓存切换。"""

import hashlib
import json
import os
import re
import stat
import time
from collections.abc import Callable
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from shutil import copytree, rmtree
from threading import RLock, get_ident
from zipfile import ZipFile

import requests

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from arknights_mower import __rootdir__, __version__
from arknights_mower.utils.github_download import request_download
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.res_version import (
    BUILDING_SKILL_DATA,
    BUILDING_SKILL_PACKAGE_PATH,
    is_package_file,
    parse_version,
)
from arknights_mower.utils.resource_ota import MAX_BYTES, OTA_MARKER, apply_ota
from arknights_mower.utils.resource_store import (
    MARKER as _RESOURCE_MARKER,
)
from arknights_mower.utils.resource_store import (
    read_index,
    read_index_state,
    read_manifest,
    resource_newer,
    select_resource,
    validate_package,
)
from arknights_mower.utils.update_runtime import write_json
from arknights_mower.utils.zip_safe import is_unsafe_zip_member

RESOURCE_OVERLAY = get_path("@app/resources", space="")
_STAGING = RESOURCE_OVERLAY / f".staging-{os.getpid()}"
_INSTALL_LOCK_PATH = RESOURCE_OVERLAY / "install.lock"
_LEGACY_SHARED_RESOURCE_OVERLAY = get_path("@app/tmp/resource", space="")
_LEGACY_RESOURCE_OVERLAY = get_path("@app/tmp/resource")
RESOURCE_REPO = "ArkMowers/MowerResource"
RESOURCE_ZIP_URL = (
    f"https://github.com/{RESOURCE_REPO}/releases/latest/download/resource.zip"
)
RESOURCE_UPDATE_URL = (
    f"https://github.com/{RESOURCE_REPO}/releases/latest/download/resource-update.json"
)
_PKG_PREFIX = "arknights_mower/"
_install_lock = RLock()
_reload_callbacks: dict[str, Callable[[], None]] = {}
_loaded_resource_signature = None
_rejected_resource_signature = None
_active_resource = None
_task_owner = None
_LOCK_POLL_INTERVAL = 0.05


def _lock_file(lock):
    if os.name == "nt":
        lock.seek(0)
        if not lock.read(1):
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(lock):
    if os.name == "nt":
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


@contextmanager
def _resource_install_guard(timeout=60):
    deadline = time.monotonic() + timeout
    _INSTALL_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _INSTALL_LOCK_PATH.open("a+b") as lock:
        while True:
            try:
                _lock_file(lock)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("等待其他 mower 实例完成资源更新超时")
                time.sleep(_LOCK_POLL_INTERVAL)
        try:
            yield
        finally:
            _unlock_file(lock)


def _resource_signature():
    def read(path):
        try:
            return path.read_bytes()
        except OSError:
            return b""

    return (
        str(RESOURCE_OVERLAY),
        read(RESOURCE_OVERLAY / "index.json"),
        read(Path(__rootdir__) / "data/version.json"),
    )


def _remember_loaded_resource():
    global _loaded_resource_signature
    _loaded_resource_signature = _resource_signature()


def _write_index(packages, *, builtin_version=None):
    index = {"packages": packages}
    if builtin_version is not None:
        index["builtin_version"] = builtin_version
    write_json(RESOURCE_OVERLAY / "index.json", index)


def _selection():
    global _active_resource
    if _active_resource is None:
        _active_resource = select_resource(
            RESOURCE_OVERLAY, Path(__rootdir__), __version__
        )
    return _active_resource


def migrate_legacy_resource_overlay():
    """复制旧共享目录或旧实例目录；保留原件供旧版本和失败恢复使用。"""
    try:
        with _resource_install_guard():
            if (RESOURCE_OVERLAY / "index.json").exists():
                return False
            candidates = []
            for legacy in dict.fromkeys(
                (_LEGACY_SHARED_RESOURCE_OVERLAY, _LEGACY_RESOURCE_OVERLAY)
            ):
                if not (legacy / _RESOURCE_MARKER).exists():
                    continue
                try:
                    manifest = validate_package(legacy, __version__)
                    candidates.append((legacy, manifest))
                except (OSError, ValueError, TypeError) as error:
                    logger.warning(f"跳过无效的旧资源目录 {legacy}：{error}")
            if not candidates:
                return False
            legacy, manifest = candidates[0]
            for other, version in candidates[1:]:
                if resource_newer(version, manifest):
                    legacy, manifest = other, version
            rmtree(_STAGING, ignore_errors=True)
            copytree(legacy, _STAGING)
            # Include the source path to avoid colliding with uploaded ZIP digests.
            name = hashlib.sha256(
                (str(legacy) + json.dumps(manifest, sort_keys=True)).encode()
            ).hexdigest()
            target = RESOURCE_OVERLAY / "packages" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                os.replace(_STAGING, target)
            _write_index([name])
            rmtree(_STAGING, ignore_errors=True)
            logger.info(f"已将旧资源复制到共享持久目录：{target}")
            return True
    except Exception as error:
        rmtree(_STAGING, ignore_errors=True)
        logger.warning(f"迁移旧资源目录失败：{error}")
        return False


def register_resource_reload(callback: Callable[[], None]):
    _reload_callbacks[f"{callback.__module__}.{callback.__qualname__}"] = callback
    return callback


def reload_resource_caches():
    for callback in tuple(_reload_callbacks.values()):
        callback()


def _reload_selected_resource():
    global _active_resource, _rejected_resource_signature
    signature = _resource_signature()
    previous = _selection()
    selected = select_resource(RESOURCE_OVERLAY, Path(__rootdir__), __version__)
    if selected == previous:
        _remember_loaded_resource()
        return False
    _active_resource = selected
    try:
        reload_resource_caches()
    except Exception:
        _active_resource = previous
        _rejected_resource_signature = signature
        reload_resource_caches()
        if selected.root is not None:
            _write_index(
                [
                    name
                    for name in read_index(RESOURCE_OVERLAY)
                    if name != selected.root.name
                ]
            )
        _remember_loaded_resource()
        raise
    _rejected_resource_signature = None
    _remember_loaded_resource()
    logger.info(
        f"已在任务边界加载资源：{selected.manifest.get('res_version', '内置资源')}"
    )
    return True


def reload_resource_caches_if_changed():
    """只有任务线程自身或已停止的实例可以切换当前进程的整套资源。"""
    with _install_lock:
        if _task_owner is not None and _task_owner != get_ident():
            return False
        if _resource_signature() in (
            _loaded_resource_signature,
            _rejected_resource_signature,
        ):
            return False
        try:
            with _resource_install_guard(timeout=0):
                return _reload_selected_resource()
        except TimeoutError:
            return False


def refresh_resource_at_boundary():
    try:
        return reload_resource_caches_if_changed()
    except Exception:
        logger.exception("新资源加载失败，继续使用原资源")
        return False


@contextmanager
def resource_task_session():
    """串行化开始任务与后台刷新；执行期间由任务线程在安全边界主动刷新。"""
    global _task_owner
    with _install_lock:
        _task_owner = get_ident()
        try:
            reload_resource_caches_if_changed()
        except Exception:
            _task_owner = None
            raise
    try:
        yield
    finally:
        with _install_lock:
            _task_owner = None
            try:
                reload_resource_caches_if_changed()
            except Exception:
                logger.exception("任务结束后刷新资源失败，保留原资源")


def resource_pkg_path(rel):
    """包管理文件从当前固定版本整包读取；未纳入资源包的文件仍属程序本体。"""
    selected = _selection()
    package_rel = BUILDING_SKILL_PACKAGE_PATH if rel == BUILDING_SKILL_DATA else rel
    managed = is_package_file(package_rel)
    if selected.root is not None and managed:
        return selected.root / package_rel
    builtin_rel = rel[len(_PKG_PREFIX) :] if rel.startswith(_PKG_PREFIX) else rel
    return Path(__rootdir__) / builtin_rel


def resource_ui_path(rel, *, source=False):
    selected = _selection()
    if selected.root is None:
        return None
    return selected.root / "ui" / ("src" if source else "public") / rel


def _asset_descriptor(asset, version, *, from_version=None):
    """Derive download URLs solely from validated MowerResource release names."""
    expected = (
        f"resource-ota_{from_version}_to_{version}.zip"
        if from_version
        else "resource.zip"
    )
    if (
        not isinstance(version, str)
        or parse_version(version) is None
        or from_version is not None
        and (not isinstance(from_version, str) or parse_version(from_version) is None)
        or not isinstance(asset, dict)
        or asset.get("name") != expected
        or type(asset.get("size")) is not int
        or not 0 < asset["size"] <= MAX_BYTES
        or not isinstance(asset.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"])
    ):
        raise ValueError("资源下载附件清单无效")
    return {
        **asset,
        "url": f"https://github.com/{RESOURCE_REPO}/releases/download/{version}/{expected}",
        "ota": from_version is not None,
    }


def _fetch_resource_update_index():
    try:
        with request_download(
            requests, "get", RESOURCE_UPDATE_URL, timeout=15, stream=True
        )[0] as response:
            raw = bytearray()
            deadline = time.monotonic() + 30
            for chunk in response.iter_content(64 * 1024):
                raw.extend(chunk)
                if time.monotonic() >= deadline:
                    raise TimeoutError("资源 OTA 索引下载超时")
                if len(raw) > 64 * 1024:
                    raise ValueError("资源更新索引过大")
            index = json.loads(raw)
        if (
            not isinstance(index, dict)
            or type(index.get("format")) is not int
            or index["format"] != 1
        ):
            raise ValueError("资源更新索引格式无效")
        return index
    except Exception as error:
        logger.debug(f"资源 OTA 索引不可用，使用整包：{error}")
        return None


def resource_ota_full_asset(data):
    """Return a verified target-release full descriptor only for a resource OTA."""
    try:
        with ZipFile(BytesIO(data)) as archive:
            if OTA_MARKER not in archive.namelist():
                return None
            if archive.getinfo(OTA_MARKER).file_size > 16 * 1024**2:
                raise ValueError("资源 OTA 清单过大")
            manifest = json.loads(archive.read(OTA_MARKER))
        if manifest.get("kind") != "mower-resource-ota":
            raise ValueError("资源 OTA 格式无效")
        return _asset_descriptor(manifest.get("full"), manifest.get("to"))
    except Exception:
        return None


def download_resource_pkg(callback=None, *, asset=None, prefer_ota=True):
    report = callback or (lambda **values: None)
    full = None
    if asset is None and (index := _fetch_resource_update_index()) is not None:
        try:
            version = index.get("version")
            full = _asset_descriptor(index.get("full"), version)
            asset = full
            current = _selection().manifest.get("res_version")
            candidates = index.get("ota", [])
            if not isinstance(candidates, list) or len(candidates) > 4:
                raise ValueError("资源 OTA 附件数量无效")
            for candidate in candidates if prefer_ota else []:
                if isinstance(candidate, dict) and candidate.get("from") == current:
                    ota = _asset_descriptor(candidate, version, from_version=current)
                    if ota["size"] < full["size"]:
                        asset = ota
                        break
        except (ValueError, TypeError):
            asset = full
    url = asset["url"] if asset else RESOURCE_ZIP_URL
    message = (
        "正在下载资源 OTA 增量包" if asset and asset.get("ota") else "正在下载资源包"
    )
    try:
        with request_download(requests, "get", url, timeout=60, stream=True)[
            0
        ] as response:
            total = int(response.headers.get("Content-Length") or 0)
            if total > MAX_BYTES:
                raise ValueError("资源下载超过 512 MiB 限制")
            current = 0
            data = BytesIO()
            digest = hashlib.sha256()
            deadline = time.monotonic() + 300
            report(
                phase="downloading",
                message=message,
                current=0,
                total=total,
                progress=0 if total else None,
            )
            for chunk in response.iter_content(64 * 1024):
                current += len(chunk)
                if current > MAX_BYTES or asset and current > asset["size"]:
                    raise ValueError("资源下载超过声明大小")
                if time.monotonic() >= deadline:
                    raise TimeoutError("资源下载超时")
                digest.update(chunk)
                data.write(chunk)
                report(
                    phase="downloading",
                    message=message,
                    current=current,
                    total=total,
                    progress=min(80, round(current / total * 80, 1)) if total else None,
                )
            if asset and (
                current != asset["size"] or digest.hexdigest() != asset["sha256"]
            ):
                raise ValueError("资源下载大小或 SHA-256 校验失败")
            return data.getvalue()
    except Exception as error:
        logger.warning(f"资源包下载失败: {error}")
        if asset and asset.get("ota") and full:
            report(
                phase="downloading",
                message="资源 OTA 下载失败，改用完整资源包",
                progress=0,
                current=0,
                total=full["size"],
            )
            return download_resource_pkg(callback, asset=full, prefer_ota=False)
    return None


def _extract_package(data, callback=None):
    report = callback or (lambda **values: None)
    report(phase="validating", message="正在检查资源包", progress=82)
    rmtree(_STAGING, ignore_errors=True)
    with ZipFile(BytesIO(data)) as archive:
        names = archive.namelist()
        if OTA_MARKER in names:
            selection = _selection()

            def source_file(name):
                source = resource_pkg_path(name)
                if selection.root is not None:
                    root = selection.root
                elif name.startswith("ui/"):
                    # Bundled UI images may be outside the Python package.
                    root = Path(__rootdir__).parent / "ui"
                    source = root / name.removeprefix("ui/")
                    if not source.exists() and name.startswith("ui/public/"):
                        source = root / "dist" / name.removeprefix("ui/public/")
                else:
                    root = Path(__rootdir__)
                if not source.resolve().is_relative_to(root.resolve()):
                    raise ValueError("资源 OTA 起点文件越出资源目录")
                return source

            apply_ota(
                archive,
                _STAGING,
                from_version=selection.manifest.get("res_version"),
                source_file=source_file,
                allowed_file=is_package_file,
                callback=callback,
            )
            return validate_package(_STAGING, __version__)
        if _RESOURCE_MARKER not in names:
            raise ValueError("资源包缺少版本清单")
        if (
            len(names) != len(set(names))
            or sum(item.file_size for item in archive.infolist()) > 512 * 1024**2
        ):
            raise ValueError("资源包包含重复路径或解压体积过大")
        for item in archive.infolist():
            name = item.filename
            if (
                is_unsafe_zip_member(name)
                or "\\" in name
                or stat.S_ISLNK(item.external_attr >> 16)
            ):
                raise ValueError("资源包含非法路径或符号链接")
            if not item.is_dir() and not is_package_file(name):
                raise ValueError(f"资源包包含未声明文件：{name}")
        members = archive.infolist()
        total = sum(member.file_size for member in members) or 1
        extracted = 0
        for member in members:
            archive.extract(member, _STAGING)
            extracted += member.file_size
            report(
                phase="extracting",
                message="正在解压资源包",
                progress=84 + round(extracted / total * 10, 1),
            )
    return validate_package(_STAGING, __version__)


def install_resource_pkg(data, callback=None):
    """原子发布不可变版本。正在运行的实例保持原版本，到任务边界再加载。"""
    report = callback or (lambda **values: None)
    # Always acquire the process lock before the file lock, also during reload.
    with _install_lock:
        try:
            with _resource_install_guard():
                manifest = _extract_package(data, callback)
                current = select_resource(
                    RESOURCE_OVERLAY, Path(__rootdir__), __version__
                )
                if manifest.get("res_version") != current.manifest.get(
                    "res_version"
                ) and not resource_newer(
                    manifest, current.manifest, allow_same_day=True
                ):
                    raise ValueError("资源包不新于当前可用资源，保留当前版本")
                report(phase="installing", message="正在应用资源包", progress=96)
                previous = _selection()
                index = read_index_state(RESOURCE_OVERLAY)
                packages = index["packages"]
                name = hashlib.sha256(data).hexdigest()
                target = RESOURCE_OVERLAY / "packages" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    os.replace(_STAGING, target)
                updated = [package for package in packages if package != name] + [name]
                builtin_version = read_manifest(
                    Path(__rootdir__) / "data/version.json"
                )["res_version"]
                try:
                    _write_index(updated, builtin_version=builtin_version)
                    if _task_owner is None or _task_owner == get_ident():
                        _reload_selected_resource()
                except Exception:
                    _write_index(packages, builtin_version=index["builtin_version"])
                    # Published generations are retained: another old process may
                    # still have pinned their paths. Only the index rolls back.
                    assert _selection() == previous
                    _remember_loaded_resource()
                    raise
                logger.info(
                    f"资源包已发布到共享持久目录：{target}，运行实例将在任务边界加载"
                )
                return True
        except Exception as error:
            logger.exception(f"资源包安装失败，保留原版本：{error}")
            return False
        finally:
            rmtree(_STAGING, ignore_errors=True)


migrate_legacy_resource_overlay()
_selection()
_remember_loaded_resource()
