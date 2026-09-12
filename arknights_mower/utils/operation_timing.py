"""按房间统计同步操作的墙钟耗时，不保存截图或逐帧数据。"""

import json
from contextvars import ContextVar
from functools import wraps
from inspect import signature
from time import perf_counter

_current = ContextVar("operation_timing", default=None)


class OperationTiming:
    def __init__(self):
        self.started = perf_counter()
        self.stack = []
        self.steps = {}
        self.retries = 0

    def enter(self, name):
        frame = [name, perf_counter(), 0.0]
        self.stack.append(frame)
        return frame

    def leave(self, frame):
        elapsed = perf_counter() - frame[1]
        self.stack.pop()
        if self.stack:
            self.stack[-1][2] += elapsed
        step = self.steps.setdefault(frame[0], {"count": 0, "total_s": 0, "own_s": 0})
        step["count"] += 1
        step["total_s"] += elapsed
        step["own_s"] += max(0, elapsed - frame[2])

    def report(self, room, outcome):
        total = perf_counter() - self.started
        own = sum(step["own_s"] for step in self.steps.values())
        return {
            "room": room,
            "outcome": outcome,
            "total_s": round(total, 3),
            "other_s": round(max(0, total - own), 3),
            "retries": self.retries,
            "steps": {
                key: {k: round(v, 3) for k, v in value.items()}
                for key, value in self.steps.items()
            },
        }


def timed_step(name):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
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


def record_selection_retry():
    timing = _current.get()
    if timing is not None:
        timing.retries += 1


def timed_room(function):
    parameters = signature(function)

    @wraps(function)
    def wrapped(*args, **kwargs):
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

            logger.info(
                "换班耗时统计 "
                + json.dumps(timing.report(room, outcome), ensure_ascii=False)
            )

    return wrapped
