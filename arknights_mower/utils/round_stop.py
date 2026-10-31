"""保存本次运行的停止请求，由任务线程在正常收尾点处理。"""

from threading import RLock

from arknights_mower.utils import config
from arknights_mower.utils.log import logger

_lock = RLock()
_requested = False


def pending():
    with _lock:
        return _requested


def request_stop():
    global _requested
    with _lock:
        if config.stop_mower.is_set():
            return False
        _requested = True
        return True


def cancel():
    global _requested
    with _lock:
        _requested = False


def finish_if_requested():
    """先保存运行状态，再取消自动恢复；调用方负责通知和退出。"""
    global _requested
    with _lock:
        if not _requested or config.stop_mower.is_set():
            return False
        from arknights_mower.solvers.record import save_current_state
        from arknights_mower.utils import crash_recovery
        from arknights_mower.utils.instance_supervisor import task_intent
        from arknights_mower.utils.update_runtime import record_task_stop

        if save_current_state() is False:
            raise RuntimeError("保存运行状态失败，保留本轮结束后停止请求")
        try:
            record_task_stop()
        except Exception:
            logger.exception("记录进程替换期间的停止选择失败，继续停止当前任务")
        try:
            task_intent(False)
        except Exception:
            logger.exception("记录任务停止意图失败，继续停止当前任务")
        config.stop_mower.set()
        _requested = False
        try:
            crash_recovery.cancel()
        except Exception:
            logger.exception("记录自动恢复取消失败，当前进程已停止后台重试")
        return True
