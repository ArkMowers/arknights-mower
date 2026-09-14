"""按房间统计同步操作的墙钟耗时，不保存截图或逐帧数据。"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from inspect import signature
from time import perf_counter
from typing import ParamSpec, TypedDict, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


@dataclass
class TimingFrame:
    name: str
    started: float
    child_seconds: float = 0.0


class StepTiming(TypedDict):
    count: int
    total_s: float
    own_s: float


class TimingReport(TypedDict):
    room: str
    outcome: str
    total_s: float
    other_s: float
    retries: int
    steps: dict[str, StepTiming]


_current: ContextVar[OperationTiming | None] = ContextVar(
    "operation_timing", default=None
)


class OperationTiming:
    def __init__(self) -> None:
        self.started = perf_counter()
        self.stack: list[TimingFrame] = []
        self.steps: dict[str, StepTiming] = {}
        self.retries = 0

    def enter(self, name: str) -> TimingFrame:
        frame = TimingFrame(name, perf_counter())
        self.stack.append(frame)
        return frame

    def leave(self, frame: TimingFrame) -> None:
        elapsed = perf_counter() - frame.started
        self.stack.pop()
        if self.stack:
            self.stack[-1].child_seconds += elapsed
        step = self.steps.setdefault(frame.name, {"count": 0, "total_s": 0, "own_s": 0})
        step["count"] += 1
        step["total_s"] += elapsed
        step["own_s"] += max(0, elapsed - frame.child_seconds)

    def report(self, room: str, outcome: str) -> TimingReport:
        total = perf_counter() - self.started
        own = sum(step["own_s"] for step in self.steps.values())
        return {
            "room": room,
            "outcome": outcome,
            "total_s": round(total, 3),
            "other_s": round(max(0, total - own), 3),
            "retries": self.retries,
            "steps": {
                key: {
                    "count": value["count"],
                    "total_s": round(value["total_s"], 3),
                    "own_s": round(value["own_s"], 3),
                }
                for key, value in self.steps.items()
            },
        }


def timed_step(name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            timing = _current.get()
            if timing is None:
                return function(*args, **kwargs)
            frame = timing.enter(name)
            try:
                return function(*args, **kwargs)
            finally:
                timing.leave(frame)

        return wrapped

    return decorate


def record_selection_retry() -> None:
    timing = _current.get()
    if timing is not None:
        timing.retries += 1


def timed_room(function: Callable[P, R]) -> Callable[P, R]:
    parameters = signature(function)

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        if _current.get() is not None:
            return function(*args, **kwargs)
        room = parameters.bind(*args, **kwargs).arguments.get("room", "")
        timing = OperationTiming()
        token = _current.set(timing)
        outcome = "returned"
        try:
            return function(*args, **kwargs)
        except BaseException as error:
            outcome = type(error).__name__
            raise
        finally:
            _current.reset(token)
            from arknights_mower.utils.log import logger

            # 保留后台诊断数据，不推送到 INFO 级别的前端运行日志。
            logger.debug(
                "换班耗时统计 "
                + json.dumps(timing.report(room, outcome), ensure_ascii=False)
            )

    return wrapped
