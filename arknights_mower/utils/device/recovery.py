from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TypeVar

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.log import logger

T = TypeVar("T")


class DeviceRecoveryError(ConnectionError):
    """当前设备恢复预算耗尽；任务保留意图并在冷却后建立新的有限预算。"""


_input_reconciliation = ContextVar("input_reconciliation", default="task")


def input_reconciliation():
    return _input_reconciliation.get()


@contextmanager
def input_reconciliation_scope(mode):
    token = _input_reconciliation.set(mode)
    try:
        yield
    finally:
        _input_reconciliation.reset(token)


def wait_for_recovery(recover_once, *, retry_errors, cooldown=30.0):
    """Retain run intent while each recovery cycle has its own finite budget."""
    while not config.stop_mower.is_set():
        try:
            result = recover_once()
            if config.stop_mower.is_set():
                raise MowerExit
            return result
        except retry_errors as exc:
            logger.warning("设备恢复暂停，%.0f 秒后重新检查所选目标：%s", cooldown, exc)
            csleep(max(1.0, cooldown))
    raise MowerExit


DEFAULT_RECOVERY_RETRIES: int = 3


def recover_connection(
    connect_once: Callable[..., T],
    *,
    retries: int = DEFAULT_RECOVERY_RETRIES,
    restarts: int = 0,
    first_attempts: int | None = None,
    wait_for_device: bool = True,
) -> T:
    """Compatibility helper for bounded local connections only.

    Full simulator recovery belongs to the application session. ``restarts``
    remains accepted for old callers but never grants a new restart budget.
    """
    if (
        retries < 1
        or restarts < 0
        or (first_attempts is not None and first_attempts < 1)
    ):
        raise ValueError("连接尝试次数必须为正数，重启次数不能为负数")
    last_exc = None
    attempts = first_attempts or retries
    for attempt in range(1, attempts + 1):
        if config.stop_mower.is_set():
            raise MowerExit
        # The attempt counter is a diagnostic: a bounded retry that succeeds is
        # normal operation, and the failure warning below already names it.
        logger.debug(f"正在尝试重连设备 ({attempt}/{attempts})...")
        try:
            return connect_once(wait_for_device=wait_for_device)
        except (MowerExit, DeviceRecoveryError):
            raise
        except Exception as e:
            last_exc = e
            logger.warning(f"设备重连 ({attempt}/{attempts}) 失败：{e}")
        if config.stop_mower.is_set():
            raise MowerExit
        if attempt < attempts:
            csleep(1)
    raise DeviceRecoveryError(f"设备局部连接预算耗尽（{attempts} 次）") from last_exc
