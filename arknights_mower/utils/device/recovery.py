from collections.abc import Callable
from typing import TypeVar

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.log import logger
from arknights_mower.utils.simulator import restart_simulator

T = TypeVar("T")


class DeviceRecoveryError(ConnectionError):
    """设备恢复已耗尽；上层不得再启动另一轮连接重试或模拟器重启。"""


def recover_connection(
    connect_once: Callable[..., T],
    *,
    retries: int = 3,
    restarts: int = 2,
    first_attempts: int | None = None,
    wait_for_device: bool = True,
) -> T:
    """统一管理完整连接尝试；ADB 就绪等待属于单次连接，不启动额外恢复循环。"""
    if (
        retries < 1
        or restarts < 0
        or (first_attempts is not None and first_attempts < 1)
    ):
        raise ValueError("连接尝试次数必须为正数，重启次数不能为负数")
    last_exc = None
    for restart_count in range(restarts + 1):
        attempts = first_attempts if restart_count == 0 and first_attempts else retries
        for attempt in range(1, attempts + 1):
            if config.stop_mower.is_set():
                raise MowerExit
            logger.info(f"设备重连 {attempt}/{attempts}")
            try:
                return connect_once(
                    wait_for_device=wait_for_device or restart_count > 0
                )
            except (MowerExit, DeviceRecoveryError):
                raise
            except Exception as e:
                last_exc = e
                logger.warning(f"设备重连 {attempt}/{attempts} 失败：{e}")
            if config.stop_mower.is_set():
                raise MowerExit
            if attempt < attempts:
                csleep(1)
        if restart_count == restarts:
            break
        logger.warning(f"设备重连 {attempts} 次仍失败，尝试重启模拟器")
        if not restart_simulator():
            raise DeviceRecoveryError("模拟器重启失败，停止设备恢复") from last_exc
    raise DeviceRecoveryError(
        f"设备连接失败，重启模拟器 {restarts} 次后仍无法恢复"
    ) from last_exc
