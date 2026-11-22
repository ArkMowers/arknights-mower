from contextvars import ContextVar
from datetime import datetime
from functools import wraps
from weakref import ref

# 仅记录本次 screencap 已取得的画面，不延长恢复探针帧的生命周期。
_received = ContextVar("received_capture_time", default=None)


class CaptureRequest:
    def __init__(self):
        self.requested_at = None

    def start(self):
        if _received.get() is not None:
            self.requested_at = datetime.now()
        return self

    def received(self, frame):
        if self.requested_at is not None:
            _received.set((ref(frame), self.requested_at))
        return frame


class CapturedFrame(tuple):
    """保留截图三元组及其 RGB 画面的采集请求时间。"""

    def __new__(cls, frame, requested_at=None):
        result = super().__new__(cls, frame)
        result.requested_at = requested_at
        return result


def with_capture_time(screencap):
    @wraps(screencap)
    def capture(*args, **kwargs):
        token = _received.set((None, None))
        try:
            frame = screencap(*args, **kwargs)
            rgb_ref, requested_at = _received.get()
            if rgb_ref is None or rgb_ref() is not frame[1]:
                requested_at = None
            return CapturedFrame(frame, requested_at)
        finally:
            _received.reset(token)

    return capture
