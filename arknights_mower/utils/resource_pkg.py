"""共享持久资源包：不可变版本目录、整包选择和任务边界缓存切换。"""

import hashlib
import json
import os
import stat
import time
from collections.abc import Callable
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from shutil import copytree, rmtree
from threading import RLock, get_ident
from uuid import uuid4
from zipfile import ZipFile

import requests

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from arknights_mower import __rootdir__, __version__
from arknights_mower.utils.github_download import download_url
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.res_version import (
    RES_PACKAGE_DATA,
    RES_PACKAGE_DIRS,
    RES_PACKAGE_MODELS,
)
from arknights_mower.utils.resource_store import (
    MARKER as _RESOURCE_MARKER,
)
from arknights_mower.utils.resource_store import (
    read_index,
    resource_newer,
    select_resource,
    validate_package,
)
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


def _write_index(packages):
    RESOURCE_OVERLAY.mkdir(parents=True, exist_ok=True)
    temporary = RESOURCE_OVERLAY / f".index-{uuid4().hex}.json"
    try:
        temporary.write_text(json.dumps({"packages": packages}), encoding="utf-8")
        os.replace(temporary, RESOURCE_OVERLAY / "index.json")
    finally:
        temporary.unlink(missing_ok=True)


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
    managed = (
        rel == _RESOURCE_MARKER
        or rel in (*RES_PACKAGE_DATA, *RES_PACKAGE_MODELS)
        or any(rel.startswith(d + "/") for d in RES_PACKAGE_DIRS)
    )
    if selected.root is not None and managed:
        return selected.root / rel
    builtin_rel = rel[len(_PKG_PREFIX) :] if rel.startswith(_PKG_PREFIX) else rel
    return Path(__rootdir__) / builtin_rel


def resource_ui_path(rel, *, source=False):
    selected = _selection()
    if selected.root is None:
        return None
    return selected.root / "ui" / ("src" if source else "public") / rel


def download_resource_pkg():
    try:
        response = requests.get(download_url(RESOURCE_ZIP_URL), timeout=60)
        if response.status_code == 200:
            return response.content
        logger.warning(f"资源包下载失败: HTTP {response.status_code}")
    except Exception as error:
        logger.warning(f"资源包下载失败: {error}")
    return None


def _extract_package(data):
    rmtree(_STAGING, ignore_errors=True)
    with ZipFile(BytesIO(data)) as archive:
        names = archive.namelist()
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
            if not item.is_dir() and not (
                name == _RESOURCE_MARKER
                or name in (*RES_PACKAGE_DATA, *RES_PACKAGE_MODELS)
                or any(name.startswith(d + "/") for d in RES_PACKAGE_DIRS)
            ):
                raise ValueError(f"资源包包含未声明文件：{name}")
        archive.extractall(_STAGING)
    return validate_package(_STAGING, __version__)


def install_resource_pkg(data):
    """原子发布不可变版本。正在运行的实例保持原版本，到任务边界再加载。"""
    # Always acquire the process lock before the file lock, also during reload.
    with _install_lock:
        try:
            with _resource_install_guard():
                manifest = _extract_package(data)
                current = select_resource(
                    RESOURCE_OVERLAY, Path(__rootdir__), __version__
                )
                if manifest.get("res_version") != current.manifest.get(
                    "res_version"
                ) and not resource_newer(manifest, current.manifest):
                    raise ValueError("资源包不新于当前可用资源，保留当前版本")
                previous = _selection()
                packages = read_index(RESOURCE_OVERLAY)
                name = hashlib.sha256(data).hexdigest()
                target = RESOURCE_OVERLAY / "packages" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    os.replace(_STAGING, target)
                updated = list(dict.fromkeys([*packages, name]))
                try:
                    _write_index(updated)
                    if _task_owner is None or _task_owner == get_ident():
                        _reload_selected_resource()
                except Exception:
                    _write_index(packages)
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
