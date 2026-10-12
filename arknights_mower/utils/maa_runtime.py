"""Validate desktop MAA core identity before acquiring a connection."""

import importlib
import json
import sys
from pathlib import Path

from arknights_mower.utils.maa_backup import (
    MaaCallError,
    VerifiedAsst,
    maa_in_use,
    update_transaction,
)
from arknights_mower.utils.maa_update import (
    MaaUpdateError,
    _find_maa_core_library,
    clear_loaded_maa_cache,
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
            asst_type._mower_core_loads = (library, count, owned)
    if not loaded_resources:
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
        raise MaaCallError("load", detail=detail)
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
