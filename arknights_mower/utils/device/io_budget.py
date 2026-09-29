"""Propagate a session deadline through synchronous device/helper startup I/O."""

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar

from arknights_mower.utils.csleep import csleep

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
