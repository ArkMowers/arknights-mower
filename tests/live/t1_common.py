"""T1 三项共享工具（实机脚本，不参与门禁 G1 收集）。

本模块只提供**无副作用**的辅助原语，供 `tests/live/t1_*.py` 复用：

| 原语 | 用途 |
|---|---|
| `quiet_logs` | `utils/log.py:50` 把 level 硬编码为 DEBUG，探测前统一抬到 INFO |
| `sha256_file` | 只读保证的取证手段（跑前跑后比对用户文件） |
| `idle_wait` | 观察者线程的**有界等待**，刻意独立于 pause 协议 |
| `no_save_conf` | 把 `config.save_conf` 换成记录器，绝不写用户的 `conf.yml` |
| `WallClockStop` | `--seconds` 墙钟上限：到点强制 `request_stop()` |
| `LogCapture` | 挂 handler 到 `utils.log.logger`，逐行收集本进程后续日志 |
| `db_backup` | `tmp/mower.db` 的 Copy-Item 备份 + `finally` 还原 |
| `install_tap_guard` | 把 `tap/swipe/swipe_path` 换成记录器，保证实机**零点击** |

⚠️ 本文件名**不以 `_tests.py` 结尾**，因此不会被 G1 的 `discover` 收集。
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import threading
from contextlib import contextmanager
from pathlib import Path

# 观察者采样窗口。AGENTS.md 规则 6 禁止 time.sleep；观察者一律走
# `threading.Event.wait`（见 `idle_wait` 的 docstring），并把单次等待保持在
# §10.2 豁免规则 3 要求的"短暂且有界"范围内。
OBSERVE_SLICE_SECONDS = 2.0

# `WallClockStop` 的硬性安全网宽限。
#
# §10.2 要求 `--seconds` 到点强制 `request_stop()`。执行该动作的是**观察者自己**
# （观察窗口结束时显式调用），定时器只是防"观察者本身也挂住"的安全网，因此必须
# **严格晚于**观察窗口 —— 否则两者在同一瞬间触发，任何"窗口末尾还在跑吗"的
# 判据都会读到刚被停掉的线程：那是竞态，会假红（本脚本首版实测踩到）。
CLOCK_GRACE_SECONDS = 10


def quiet_logs() -> None:
    """只提高本进程 logger level，不碰 log.py，也不影响落盘日志。"""
    from arknights_mower.utils.log import logger

    logger.setLevel(logging.INFO)
    for handler in logger.handlers:
        handler.setLevel(logging.INFO)


def sha256_file(path: Path) -> str:
    """返回文件 SHA256；文件不存在时返回 `<missing>`。"""
    if not path.is_file():
        return "<missing>"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def idle_wait(seconds: float) -> None:
    """观察者线程的有界等待。

    刻意**不用** `pause.wait()`：观察者会被同一个 pause 挂起，
    使 pause/stop 验证**恒真**（S13 规则 6 / T1 规约 1 的陷阱）。
    也**不用** `time.sleep`（AGENTS.md 规则 6）。`Event.wait` 与 pause 协议无关。
    """
    if seconds <= 0:
        return
    threading.Event().wait(seconds)


@contextmanager
def no_save_conf():
    """把 `config.save_conf` 换成记录器，并 yield 该调用记录列表。

    `SchedulerState._init_and_validate`（拆分后位于 `state_plan_load.py:156-161`）
    在 `dorm_order == ""` 时会调 `config.save_conf()`，**会写用户的 `conf.yml`**。
    所有构造 `SchedulerState` 的探测都必须先套上本上下文；yield 出的列表
    记录被拦截的调用次数，是"未写 conf.yml"的直接证据。
    """
    from arknights_mower.utils import config

    calls: list = []
    original = config.save_conf
    config.save_conf = lambda *args, **kwargs: calls.append((args, kwargs))
    try:
        yield calls
    finally:
        config.save_conf = original


class WallClockStop:
    """`--seconds` 墙钟上限（S13 规则 2）的安全网。

    到点置 `timed_out=True` 并调用 `on_timeout`（通常是 `pause.request_stop`）。
    定时器线程用 `threading.Timer`（内部是 `Event.wait`），**不是** `time.sleep`。

    ⚠️ 定时器**不是**唯一的停止路径：观察者窗口结束时也要显式调一次
    `request_stop()`（覆盖正常结束与 Ctrl+C）；传入的 `seconds` 应比观察窗口
    至少多 `CLOCK_GRACE_SECONDS`，否则两者同刻触发会制造竞态。
    """

    def __init__(self, seconds: int, on_timeout=None) -> None:
        self.seconds = seconds
        self.timed_out = False
        self._on_timeout = on_timeout
        self._timer = threading.Timer(seconds, self._fire)
        self._timer.daemon = True

    def _fire(self) -> None:
        self.timed_out = True
        self.request_stop()

    def request_stop(self) -> None:
        if self._on_timeout is not None:
            self._on_timeout()

    def start(self) -> "WallClockStop":
        self._timer.start()
        return self

    def cancel(self) -> None:
        self._timer.cancel()


@contextmanager
def db_backup(db_path: Path):
    """`tmp/mower.db` 的 Copy-Item 备份 + `finally` 还原。

    不用 `git checkout`（会丢未提交成果）；数据库不在 git 索引里，
    这里用文件级备份/还原，并删除临时备份文件。
    """
    backup = db_path.with_name(db_path.name + ".t1bak")
    existed = db_path.is_file()
    if existed:
        shutil.copy2(db_path, backup)
    try:
        yield backup
    finally:
        if backup.is_file():
            if existed:
                shutil.copy2(backup, db_path)
            backup.unlink()


def install_tap_guard(port) -> list:
    """把 `tap`/`swipe`/`swipe_path` 替换成记录器，返回调用列表。

    T1 全程**不得 tap / swipe**。本守卫保证即使某个 planner 意外产出任务，
    点击也不会到达真机；调用列表用于事后断言计数为 0。
    """
    calls: list = []

    def _recorder(kind: str):
        def _fn(*args, **kwargs) -> None:
            calls.append((kind, args))

        return _fn

    for name in ("tap", "swipe", "swipe_path"):
        setattr(port, name, _recorder(name))
    return calls


class LogCapture:
    """挂一个 handler 到 `utils.log.logger`，逐行收集日志消息。

    所有模块都 `from arknights_mower.utils.log import logger` 复用同一个
    logger 对象，因此挂在它上面的 handler 能看到全部记录。
    """

    def __init__(self) -> None:
        self.lines: list[str] = []
        self._handler: logging.Handler | None = None

    def __enter__(self) -> "LogCapture":
        from arknights_mower.utils.log import logger

        capture = self

        class _CaptureHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                try:
                    capture.lines.append(record.getMessage())
                except Exception:
                    pass

        self._handler = _CaptureHandler()
        self._handler.setLevel(logging.DEBUG)
        logger.addHandler(self._handler)
        return self

    def __exit__(self, *exc_info) -> bool:
        from arknights_mower.utils.log import logger

        if self._handler is not None:
            logger.removeHandler(self._handler)
        return False

    def count(self, needle: str) -> int:
        return sum(1 for line in self.lines if needle in line)

    def find(self, needle: str) -> list[str]:
        return [line for line in self.lines if needle in line]
