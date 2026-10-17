"""Propagate a session deadline through synchronous device/helper startup I/O."""

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic

from arknights_mower.utils.csleep import cancellation_scope, csleep

_remaining: ContextVar[Callable[[], float] | None] = ContextVar(
    "device_io_remaining", default=None
)


def io_timeout(maximum: float) -> float:
    remaining = _remaining.get()
    return min(maximum, remaining()) if remaining is not None else maximum


def budget_sleep(seconds: float) -> None:
    csleep(io_timeout(seconds))
    io_timeout(0)


@contextmanager
def touch_release_budget():
    """仅为已按下的触摸释放保留一秒清理预算，不发送新的手势。"""
    deadline = monotonic() + 1

    def remaining():
        seconds = deadline - monotonic()
        if seconds <= 0:
            raise TimeoutError("触摸释放清理超时")
        return seconds

    token = _remaining.set(remaining)
    try:
        with cancellation_scope(lambda: False):
            yield
    finally:
        _remaining.reset(token)


@contextmanager
def device_io_budget(remaining: Callable[[], float]):
    parent = _remaining.get()

    def available():
        return min(parent(), remaining()) if parent is not None else remaining()

    token = _remaining.set(available)
    try:
        available()
        yield
        available()
    finally:
        _remaining.reset(token)
