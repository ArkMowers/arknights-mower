"""截图的内存预览、后台存储和独立过期清理。

识别端只提交已经编码的图片，不等待磁盘。写盘队列按顺序保存所有提交的
截图，并记录待写字节数及存储耗时。
"""

import heapq
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from queue import Queue
from threading import Event, Lock, Thread
from typing import Callable

_HOUR_FOLDER = re.compile(r"\d{8}-\d{2}\Z")
_IMPORTANT_FOLDERS = {"run_order", "workshop", "solve_captcha"}


@dataclass(frozen=True)
class Screenshot:
    filename: str
    data: bytes
    captured_ns: int
    queued_at: float
    preview: bool


class ScreenshotStore:
    def __init__(
        self,
        folder: Path,
        retention_hours: Callable[[], float],
        logger: logging.Logger | None = None,
        cleanup_interval: float = 30,
    ):
        self.folder = Path(folder)
        self.retention_hours = retention_hours
        self.logger = logger or logging.getLogger(__name__)
        self.cleanup_interval = cleanup_interval
        self.queue = Queue()
        self._lock = Lock()
        self._cleanup_lock = Lock()
        self._stop = Event()
        self._threads: list[Thread] = []
        self._latest: Screenshot | None = None
        self._last_saved = ""
        self._last_timestamp = 0
        self._pending_count = 0
        self._pending_bytes = 0
        self._saved = 0
        self._failed = 0
        self._write_ms = 0.0
        self._queue_wait_ms = 0.0
        self._cleanup_ms = 0.0
        self._cleanup_failed = 0
        self._last_error_log = float("-inf")

    def start(self):
        with self._lock:
            if self._threads:
                return
            for name, target in (
                ("screenshot-writer", self._writer),
                ("screenshot-cleaner", self._cleaner),
            ):
                thread = Thread(name=name, target=target, daemon=True)
                self._threads.append(thread)
                thread.start()

    def close(self, timeout=5):
        """正常关闭时排空写盘队列；磁盘卡住时不无限等待。"""
        with self._lock:
            if not self._stop.is_set():
                self._stop.set()
                self.queue.put(None)
        deadline = time.monotonic() + timeout
        for thread in self._threads:
            thread.join(max(0, deadline - time.monotonic()))

    def submit(self, img, sub_folder=None) -> str:
        # cv2.imencode 返回可变 ndarray；只复制编码数据，不复制识别用的整帧。
        data = bytes(img)
        if sub_folder and (
            Path(sub_folder).name != sub_folder
            or sub_folder in {".", ".."}
            or "\\" in sub_folder
        ):
            raise ValueError("截图子目录必须是单个目录名")
        with self._lock:
            if self._stop.is_set():
                raise RuntimeError("截图存储已关闭")
            captured_ns = max(time.time_ns(), self._last_timestamp + 1)
            self._last_timestamp = captured_ns
            folder = sub_folder or datetime.fromtimestamp(captured_ns / 10**9).strftime(
                "%Y%m%d-%H"
            )
            filename = f"{folder}/{captured_ns}.jpg"
            frame = Screenshot(
                filename, data, captured_ns, time.monotonic(), not sub_folder
            )
            if frame.preview:
                self._latest = frame
            self._pending_count += 1
            self._pending_bytes += len(data)
            self.queue.put(frame)
        return filename

    def latest(self) -> Screenshot | None:
        with self._lock:
            return self._latest

    def last_saved(self) -> str:
        with self._lock:
            return self._last_saved

    def stats(self) -> dict:
        with self._lock:
            return {
                # 包含正在写入的一帧，因此慢磁盘下也能观察真实待写占用。
                "pending_count": self._pending_count,
                "pending_bytes": self._pending_bytes,
                "saved": self._saved,
                "failed": self._failed,
                "write_ms": round(self._write_ms, 2),
                "queue_wait_ms": round(self._queue_wait_ms, 2),
                "cleanup_ms": round(self._cleanup_ms, 2),
                "cleanup_failed": self._cleanup_failed,
            }

    def _report_error(self, message, exc):
        # 持续写盘失败时避免反过来挤爆日志队列；失败总数仍逐次累加。
        now = time.monotonic()
        with self._lock:
            if now - self._last_error_log < 30:
                return
            self._last_error_log = now
        self.logger.error("%s: %s", message, exc)

    def _write(self, frame: Screenshot):
        destination = self.folder / frame.filename
        temporary = destination.with_suffix(".jpg.tmp")
        try:
            for attempt in range(2):
                destination.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with temporary.open("wb") as output:
                        output.write(frame.data)
                    break
                except FileNotFoundError:
                    # 清理线程可能刚删除了这个空目录，重建后再试一次。
                    if attempt:
                        raise
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _writer(self):
        while True:
            frame = self.queue.get()
            try:
                if frame is None:
                    return
                started = time.monotonic()
                try:
                    self._write(frame)
                except Exception as exc:
                    with self._lock:
                        self._failed += 1
                    self._report_error(f"截图写入失败 {frame.filename}", exc)
                else:
                    with self._lock:
                        self._saved += 1
                        if frame.preview:
                            self._last_saved = frame.filename
                finally:
                    with self._lock:
                        self._pending_count -= 1
                        self._pending_bytes -= len(frame.data)
                        self._write_ms = (time.monotonic() - started) * 1000
                        self._queue_wait_ms = (started - frame.queued_at) * 1000
            finally:
                self.queue.task_done()
                # 不让阻塞中的 queue.get() 留住上一帧。
                del frame

    @staticmethod
    def _timestamp(name: str) -> int | None:
        stem, suffix = os.path.splitext(name)
        if suffix != ".jpg" or not stem.isascii() or not stem.isdigit():
            return None
        if len(stem) == 14:
            try:
                return int(datetime.strptime(stem, "%Y%m%d%H%M%S").timestamp() * 10**9)
            except ValueError:
                return None
        return int(stem)

    def _images(self, folder):
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if self._stop.is_set():
                        return
                    if entry.is_file(follow_symlinks=False):
                        timestamp = self._timestamp(entry.name)
                        if timestamp is not None:
                            yield timestamp, entry.name
        except FileNotFoundError:
            return

    def _remove_expired(self, folder, cutoff_ns, keep_latest=0):
        if keep_latest:
            newest = heapq.nlargest(keep_latest, self._images(folder))
            if len(newest) < keep_latest:
                return
            # 第二遍扫描时新写入的文件比这个边界新，不会被误删。
            cutoff_ns = min(newest)[0]
        deleted = 0
        for timestamp, name in self._images(folder):
            if timestamp >= cutoff_ns:
                continue
            try:
                (folder / name).unlink(missing_ok=True)
                deleted += 1
            except OSError as exc:
                self._cleanup_error(exc)
            if deleted and deleted % 100 == 0 and self._stop.wait(0.01):
                return

    def _cleanup_error(self, exc):
        with self._lock:
            self._cleanup_failed += 1
        self._report_error("清理截图失败", exc)

    def cleanup(self):
        # 防止手动清理和定时清理重叠，不占用预览/提交的锁。
        with self._cleanup_lock:
            started = time.monotonic()
            try:
                cutoff_ns = time.time_ns() - int(
                    max(0, self.retention_hours()) * 3600 * 10**9
                )
                # 旧根目录仅做过期删除，不迁移也不建立路径映射。
                self._remove_expired(self.folder, cutoff_ns)
                if not self.folder.exists():
                    return
                with os.scandir(self.folder) as entries:
                    for entry in entries:
                        if self._stop.is_set():
                            return
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                        folder = Path(entry.path)
                        try:
                            if _HOUR_FOLDER.fullmatch(entry.name):
                                hour = datetime.strptime(entry.name, "%Y%m%d-%H")
                                if int(hour.timestamp() * 10**9) >= cutoff_ns:
                                    continue
                            self._remove_expired(
                                folder,
                                cutoff_ns,
                                100 if entry.name in _IMPORTANT_FOLDERS else 0,
                            )
                            if _HOUR_FOLDER.fullmatch(entry.name):
                                try:
                                    folder.rmdir()  # 仅删除空目录，保留写入中的 .tmp。
                                except OSError:
                                    pass
                        except (OSError, ValueError) as exc:
                            self._cleanup_error(exc)
            except Exception as exc:
                self._cleanup_error(exc)
            finally:
                with self._lock:
                    self._cleanup_ms = (time.monotonic() - started) * 1000

    def _cleaner(self):
        while not self._stop.is_set():
            self.cleanup()
            stats = self.stats()
            self.logger.debug("截图存储状态 %s", stats)
            if stats["pending_count"]:
                self.logger.debug(
                    "待写截图 %s 张 / %.2f MiB，最近排队 %.0f ms，写盘 %.0f ms",
                    stats["pending_count"],
                    stats["pending_bytes"] / 1024**2,
                    stats["queue_wait_ms"],
                    stats["write_ms"],
                )
            if self._stop.wait(self.cleanup_interval):
                return
