"""Validate desktop MAA core identity before acquiring a connection."""

from pathlib import Path

from arknights_mower.utils.maa_backup import (
    VerifiedAsst,
    identity,
    maa_in_use,
    update_transaction,
)
from arknights_mower.utils.maa_update import (
    MaaUpdateError,
    _find_maa_core_library,
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


@update_transaction
def load_verified_maa(asst_type, target, callback):
    """Reject stale native images without unloading live callbacks or handles."""
    if maa_in_use():
        raise MaaUpdateError("MAA 正在使用中，不能重新加载核心")
    target = Path(target).expanduser()
    library = _find_maa_core_library(target)
    if library is None:
        raise MaaUpdateError("MAA 安装目录缺少核心运行库")
    generation = (str(library.absolute()), identity(library))
    previous = vars(asst_type).get("_mower_core_generation")
    if previous is not None and previous[0] != generation:
        raise MaaCoreRestartRequired()
    if not asst_type.load(path=target, incremental_path=target / "cache"):
        raise MaaUpdateError("MAA 资源加载失败，请检查核心与资源版本是否匹配")
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
        if loaded != installed or generation != (
            str(library.absolute()),
            identity(library),
        ):
            raise MaaCoreRestartRequired(loaded, installed)
        asst_type._mower_core_generation = (generation, installed)
        return instance
    except Exception:
        # The connection is not acquired yet. Preserve the primary diagnosis
        # even if a damaged SDK also rejects cancellation.
        try:
            instance.stop()
        except Exception:
            pass
        raise
