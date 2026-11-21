from contextlib import contextmanager
from threading import Lock

from arknights_mower.utils import config

_lock = Lock()
_active_scopes = 0


@contextmanager
def execution():
    """嵌套任务沿用本轮的停止请求，最外层退出时清理。"""
    global _active_scopes
    with _lock:
        _active_scopes += 1
    try:
        yield
    finally:
        with _lock:
            _active_scopes -= 1
            if not _active_scopes:
                config.stop_maa.clear()


def request_stop():
    with _lock:
        if not _active_scopes or config.stop_mower.is_set():
            return False
        config.stop_maa.set()
        return True
