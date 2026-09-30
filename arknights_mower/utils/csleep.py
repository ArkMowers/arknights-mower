import time
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta

from arknights_mower.utils import config
from arknights_mower.utils.operation_timing import timed_step


class MowerExit(Exception):
    pass


_cancelled: ContextVar[Callable[[], bool] | None] = ContextVar(
    "sleep_cancelled", default=None
)


@contextmanager
def cancellation_scope(cancelled: Callable[[], bool]):
    token = _cancelled.set(cancelled)
    try:
        yield
    finally:
        _cancelled.reset(token)


@timed_step("sleep")
def csleep(interval: float = 1):
    """check and sleep"""
    stop_time = datetime.now() + timedelta(seconds=interval)
    cancelled = _cancelled.get() or config.stop_mower.is_set
    while True:
        if cancelled():
            raise MowerExit
        remaining = stop_time - datetime.now()
        if remaining > timedelta(seconds=1):
            time.sleep(1)
        elif remaining > timedelta():
            time.sleep(remaining.total_seconds())
        else:
            return
