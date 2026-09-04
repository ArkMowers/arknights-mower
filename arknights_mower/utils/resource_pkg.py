"""资源包 overlay：文件解析 + 下载 + 原子安装（#191）。

- 资源包解压到可写 ``@app/tmp/resource/``（冻结 exe 下 ``__rootdir__`` 只读，原位替换不成立），
  各加载器经 ``resource_pkg_path`` 先查 overlay、回退内置 ``__rootdir__``。
- zip 内路径相对仓库根（``arknights_mower/data/X.json``、``ui/public/depot/X.webp``）。
- 安装走「原子换目录」：staging → resource，旧目录先挪走，失败回滚；version.json 随 zip
  在整目录内原子落位（资源全成功才版本生效，失败整体回滚）。
- 切换后刷新已登记的进程内 JSON/模型缓存；刷新失败时连同目录一起回滚，无需重启进程。
"""

import os
import time
from collections.abc import Callable
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from shutil import copytree, rmtree
from threading import RLock
from zipfile import ZipFile

import requests

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from arknights_mower import __rootdir__
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.zip_safe import is_unsafe_zip_member

# 资源属于当前 mower 安装，而不是某个配置实例。manager.py 会把实例目录写入
# path.global_space，因此这里必须显式覆盖为默认应用空间；自动检查、自动更新开关仍
# 保存在各实例自己的 conf.yml 中。
RESOURCE_OVERLAY = get_path("@app/tmp/resource", space="")
_STAGING = get_path("@app/tmp/resource_staging", space="")
_OLD = get_path("@app/tmp/resource_old", space="")
_INSTALL_LOCK_PATH = get_path("@app/tmp/resource_install.lock", space="")
_LEGACY_RESOURCE_OVERLAY = get_path("@app/tmp/resource")
RESOURCE_REPO = "ArkMowers/MowerResource"
RESOURCE_ZIP_URL = (
    f"https://github.com/{RESOURCE_REPO}/releases/latest/download/resource.zip"
)
# 有效资源包的标记：zip 根相对路径里的 version.json
_RESOURCE_MARKER = "arknights_mower/data/version.json"
_PKG_PREFIX = "arknights_mower/"
_install_lock = RLock()
_reload_callbacks: dict[str, Callable[[], None]] = {}
_loaded_resource_signature: tuple[str, bytes] | None = None
_LOCK_POLL_INTERVAL = 0.05


def _lock_file(lock) -> None:
    if os.name == "nt":
        lock.seek(0)
        if not lock.read(1):
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(lock) -> None:
    if os.name == "nt":
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


@contextmanager
def _resource_install_guard(timeout: float = 60):
    """用系统文件锁串行化共享资源切换；进程退出后锁会由系统自动释放。"""
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


def _resource_signature() -> tuple[str, bytes] | None:
    """返回当前共享 overlay 标记；内容变化用于通知其他实例刷新缓存。"""
    marker = RESOURCE_OVERLAY / _RESOURCE_MARKER
    try:
        return ("overlay", marker.read_bytes())
    except OSError:
        builtin = Path(__rootdir__) / "data/version.json"
        try:
            return ("builtin", builtin.read_bytes())
        except OSError:
            return None


def _remember_loaded_resource() -> None:
    global _loaded_resource_signature
    _loaded_resource_signature = _resource_signature()


def migrate_legacy_resource_overlay() -> bool:
    """首次升级时把当前实例已有的资源复制到共享空间。"""
    if _LEGACY_RESOURCE_OVERLAY == RESOURCE_OVERLAY:
        return False
    legacy_marker = _LEGACY_RESOURCE_OVERLAY / _RESOURCE_MARKER
    if not legacy_marker.is_file():
        return False

    try:
        with _resource_install_guard():
            if RESOURCE_OVERLAY.exists():
                return False
            rmtree(_STAGING, ignore_errors=True)
            copytree(_LEGACY_RESOURCE_OVERLAY, _STAGING)
            os.replace(_STAGING, RESOURCE_OVERLAY)
    except Exception as e:
        rmtree(_STAGING, ignore_errors=True)
        logger.warning(f"迁移实例资源到共享目录失败：{e}")
        return False

    logger.info(f"已将实例资源迁移到共享目录：{RESOURCE_OVERLAY}")
    return True


def register_resource_reload(callback: Callable[[], None]) -> Callable[[], None]:
    """登记一个资源包切换后的进程内缓存刷新函数。"""
    key = f"{callback.__module__}.{callback.__qualname__}"
    _reload_callbacks[key] = callback
    return callback


def reload_resource_caches() -> None:
    """刷新当前进程里已经加载过的资源数据；任一失败都向上抛出。"""
    for callback in tuple(_reload_callbacks.values()):
        callback()


def reload_resource_caches_if_changed() -> bool:
    """共享资源被其他实例替换后刷新本进程缓存；无变化或正在安装时返回 False。"""
    if _resource_signature() == _loaded_resource_signature:
        return False
    with _install_lock:
        if _resource_signature() == _loaded_resource_signature:
            return False
        try:
            with _resource_install_guard(timeout=0):
                signature = _resource_signature()
                if signature == _loaded_resource_signature:
                    return False
                reload_resource_caches()
                _remember_loaded_resource()
        except TimeoutError:
            return False
    logger.info("检测到其他 mower 实例更新了共享资源，已刷新当前进程缓存")
    return True


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


def _install_resource_pkg_locked(data: bytes) -> bool:
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
            _remember_loaded_resource()
        except Exception as e:
            logger.exception(f"资源包进程内加载失败，正在回滚：{e}")
            try:
                if RESOURCE_OVERLAY.exists():
                    os.replace(RESOURCE_OVERLAY, _STAGING)
                if _OLD.exists():
                    os.replace(_OLD, RESOURCE_OVERLAY)
                reload_resource_caches()
                _remember_loaded_resource()
            except Exception as rollback_error:
                logger.exception(f"资源包回滚后重新加载失败：{rollback_error}")
            rmtree(_STAGING, ignore_errors=True)
            return False

        if _OLD.exists():
            rmtree(_OLD, ignore_errors=True)
        logger.info(f"资源包安装成功并已在当前进程生效：{RESOURCE_OVERLAY}")
        return True


def install_resource_pkg(data: bytes) -> bool:
    """串行切换共享资源并刷新当前进程缓存；切换或加载失败均回滚。"""
    try:
        with _resource_install_guard():
            return _install_resource_pkg_locked(data)
    except TimeoutError as e:
        logger.warning(f"资源包安装失败：{e}")
        return False


migrate_legacy_resource_overlay()
_remember_loaded_resource()
