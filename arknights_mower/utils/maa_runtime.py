"""Validate desktop MAA core identity before acquiring a connection."""

import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

from arknights_mower.utils.maa_backup import (
    MaaCallError,
    VerifiedAsst,
    identity,
    maa_in_use,
    update_transaction,
)
from arknights_mower.utils.maa_update import (
    MaaUpdateError,
    _find_maa_core_library,
    clear_loaded_maa_cache,
    missing_maa_resource_files,
    read_installed_version,
)


class MaaCoreRestartRequired(MaaUpdateError):
    code = "maa_core_restart_required"

    def __init__(self, loaded_version="", installed_version=""):
        versions = (
            f"（运行中 {loaded_version}，磁盘 {installed_version}）"
            if loaded_version and installed_version
            else ""
        )
        super().__init__(
            f"MAA 核心已更新或安装目录已改变{versions}，请重启 Mower 后再运行 MAA；"
            "停止后重新启动任务不能替代重启 Mower 进程"
        )


def _core_generation(core_path):
    try:
        resolved = core_path.resolve(strict=True)
        value = resolved.stat()
    except (OSError, RuntimeError) as error:
        raise MaaCoreRestartRequired() from error
    return (
        str(core_path.absolute()),
        str(resolved),
        (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns),
    )


def resource_load_error(target):
    detail = f"目录={target}，增量目录={target / 'cache'}"
    try:
        with (target / "resource" / "config.json").open(encoding="utf-8") as file:
            json.load(file)
    except FileNotFoundError:
        detail += "；配置文件不存在，请更新 MAA 资源或重新安装完整的 MAA"
    except PermissionError:
        detail += f"；配置文件访问被拒绝：{target / 'resource' / 'config.json'}，请关闭外部 MAA 并检查读取权限"
    except (json.JSONDecodeError, UnicodeDecodeError):
        detail += "；配置文件格式无效，请更新 MAA 资源或重新安装完整的 MAA"
    except OSError as error:
        detail += f"；配置文件读取失败：{error}"
    return MaaCallError("load", detail=detail)


def navigation_cache_path(target, *, android=False):
    resource = Path(target) / "resource"
    cache = Path(target) / "cache/resource"
    if not android and (resource / "tasks").is_dir():
        cache /= "tasks"
    return cache / "tasks.json"


@update_transaction
def load_maa_with_navigation(target, callback, download):
    """Restore the prior navigation if a downloaded overlay cannot load."""
    from arknights_mower.utils.maa_process import (
        close_idle_maa_processes,
        installation_lease,
        maa_client_guard,
    )

    target = Path(target).expanduser().absolute()
    path = navigation_cache_path(target)
    if maa_in_use():
        raise MaaUpdateError("MAA 正在使用中，不能更新活动导航")
    close_idle_maa_processes(target)
    with maa_client_guard(target):
        with installation_lease(target, exclusive=True):
            previous = None
            if path.is_file():
                with path.open("rb") as stream:
                    previous = stream.read(4 * 1024 * 1024 + 1)
                if len(previous) > 4 * 1024 * 1024:
                    raise MaaCallError(
                        "load", detail="活动导航缓存超过大小限制，请检查缓存文件"
                    )
            download(target)
            written = identity(path)
        try:
            return load_maa_process(target, callback)
        except BaseException:
            try:
                with installation_lease(target, exclusive=True):
                    # Do not replace a cache file changed by an independent writer.
                    if written is not None and identity(path) == written:
                        if previous is None:
                            path.unlink()
                        else:
                            with tempfile.NamedTemporaryFile(
                                dir=path.parent, delete=False
                            ) as stream:
                                temporary = Path(stream.name)
                                try:
                                    stream.write(previous)
                                    stream.flush()
                                except BaseException:
                                    temporary.unlink(missing_ok=True)
                                    raise
                            try:
                                os.replace(temporary, path)
                            finally:
                                temporary.unlink(missing_ok=True)
            except (OSError, MaaUpdateError) as error:
                from arknights_mower.utils.log import logger

                logger.warning(f"MAA 活动导航恢复失败，路径={path}：{error}")
            raise


@update_transaction
def load_maa_process(target, callback):
    """Verify a fresh worker before handing the device to desktop MAA."""
    from arknights_mower.utils.maa_process import MaaProcess, MaaProcessError

    if maa_in_use():
        raise MaaUpdateError("MAA 正在使用中，不能重新加载核心")
    target = Path(target).expanduser().absolute()
    missing = missing_maa_resource_files(target)
    if missing:
        raise MaaCallError(
            "load",
            detail=f"安装资源缺少 {len(missing)} 个文件，例如 {missing[0]}；请使用完整包修复",
        )
    core_path = _find_maa_core_library(target)
    if core_path is None:
        raise MaaUpdateError("MAA 安装目录缺少核心运行库")
    generation = _core_generation(core_path)
    installed = read_installed_version(target, fresh=True)
    if not installed:
        raise MaaUpdateError("无法读取磁盘 MAA 核心版本，请检查 MAA 安装")
    instance = VerifiedAsst(
        lambda callback: MaaProcess(target, callback), target, callback
    )
    try:
        if instance.get_version() != installed or generation != _core_generation(
            core_path
        ):
            raise MaaProcessError("MAA 工作进程版本与安装文件不一致，请重新初始化 MAA")
        return instance
    except BaseException:
        instance.close()
        raise


@update_transaction
def load_verified_maa(asst_type, target, callback):
    """Attempt one idle SDK reload, then retain the process-restart fallback."""
    try:
        return _load_verified_maa(asst_type, target, callback)
    except MaaCoreRestartRequired as mismatch:
        try:
            clear_loaded_maa_cache(target)
            python_path = str(Path(target).expanduser() / "Python")
            sys.path.insert(0, python_path)
            new_type = importlib.import_module("asst.asst").Asst
            if new_type is asst_type:
                raise MaaCoreRestartRequired()
            return _load_verified_maa(new_type, target, callback)
        except Exception as error:
            raise mismatch from error


def _load_verified_maa(asst_type, target, callback):
    if maa_in_use():
        raise MaaUpdateError("MAA 正在使用中，不能重新加载核心")
    target = Path(target).expanduser()
    core_path = _find_maa_core_library(target)
    if core_path is None:
        raise MaaUpdateError("MAA 安装目录缺少核心运行库")
    generation = _core_generation(core_path)
    if vars(asst_type).get("_mower_core_unusable"):
        raise MaaCoreRestartRequired()
    previous = vars(asst_type).get("_mower_core_generation")
    if previous is not None and previous[0] != generation:
        raise MaaCoreRestartRequired()
    old_library = vars(asst_type).get("_Asst__lib")
    old_loads = vars(asst_type).get("_mower_core_loads")
    if old_library is not None and (
        not isinstance(old_loads, tuple)
        or len(old_loads) != 4
        or old_loads[0] is not old_library
        or not old_loads[2]
        or old_loads[3] != generation
    ):
        raise MaaCoreRestartRequired()
    try:
        loaded_resources = asst_type.load(
            path=target, incremental_path=target / "cache"
        )
    finally:
        library = vars(asst_type).get("_Asst__lib")
        if library is not None and library is not old_library:
            owned = old_library is None or (
                old_loads is not None and old_loads[0] is old_library and old_loads[2]
            )
            count = 1 if old_loads is None else old_loads[1] + 1
            if old_library is not None and library._handle != old_library._handle:
                owned = False
            # Native opens survive failed resources, instance creation or probing.
            # Keep their identity independently of the successfully verified cache.
            asst_type._mower_core_loads = (library, count, owned, generation)
    if not loaded_resources:
        raise resource_load_error(target)
    instance = VerifiedAsst(asst_type, target, callback)
    try:
        installed = (
            previous[1]
            if previous is not None
            else read_installed_version(target, fresh=True)
        )
        if not installed:
            raise MaaUpdateError("无法读取磁盘 MAA 核心版本，请检查安装后重启 Mower")
        loaded = instance.get_version()
        if loaded != installed or generation != _core_generation(core_path):
            raise MaaCoreRestartRequired(loaded, installed)
        asst_type._mower_core_generation = (generation, installed)
        return instance
    except Exception:
        # The connection is not acquired yet. Preserve the primary diagnosis
        # even if a damaged SDK also rejects cancellation.
        try:
            instance.stop()
        except Exception:
            asst_type._mower_core_unusable = True
        del instance
        raise
