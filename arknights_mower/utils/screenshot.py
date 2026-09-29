"""截图的内存预览、后台存储和独立过期清理。

识别端提交内存帧，不等待编码或磁盘。预览编码只保留一个待处理槽位，
历史队列同时限制原始帧及 JPEG 的数量与字节数。
"""

import heapq
import json
import logging
import os
import shutil
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from threading import Condition, Event, Lock, Thread
from typing import Callable

import numpy as np

from arknights_mower.utils.log_retention import RUNTIME_LOG_RETENTION_HOURS
from arknights_mower.utils.screenshot_cleanup import (
    HOUR_FOLDER,
    IMPORTANT_FOLDERS,
    ScreenshotCleanup,
    screenshot_timestamp,
)

_ERROR_WINDOW_NS = 5 * 60 * 10**9
_RECENT_FRAME_LIMIT = 16
_RECENT_BYTE_LIMIT = 32 * 1024**2
_LOG_RETENTION_NS = RUNTIME_LOG_RETENTION_HOURS * 3600 * 10**9
_STATUS_FIELDS = (
    "pending_count",
    "pending_bytes",
    "saved",
    "failed",
    "dropped",
    "cleanup_failed",
    "preview_replaced",
    "preview_failed",
    "archive_dropped",
)


@dataclass(eq=False)
class Screenshot:
    filename: str
    data: bytes | np.ndarray
    captured_ns: int
    queued_at: float
    preview: bool
    important: bool
    _encoding: bool = field(default=False, init=False, repr=False)
    _encode_error: str | None = field(default=None, init=False, repr=False)
    _pending_bytes: int | None = field(default=None, init=False, repr=False)

    @property
    def size(self):
        return self.data.nbytes if isinstance(self.data, np.ndarray) else len(self.data)


def _encode_frame(rgb):
    # Lazy import keeps the persistence module usable without loading config.
    from arknights_mower.utils.image import img2bytes

    return img2bytes(rgb)


def _newer_than(published: Screenshot | None, frame: Screenshot) -> bool:
    """Preview capture time only moves forward, so backlog cannot age the slot."""
    return published is None or published.captured_ns < frame.captured_ns


class ScreenshotStore:
    def __init__(
        self,
        folder: Path,
        retention_hours: Callable[[], float],
        logger: logging.Logger | None = None,
        cleanup_interval: float = 3600,
        *,
        max_pending_count: int = 128,
        max_pending_bytes: int = 64 * 1024**2,
        max_recent_count: int = _RECENT_FRAME_LIMIT,
        max_recent_bytes: int = _RECENT_BYTE_LIMIT,
        encoder: Callable = _encode_frame,
        writer: Callable | None = None,
        clock: Callable[[], float] | None = None,
        wall_time_ns: Callable[[], int] | None = None,
        cleanup_batch_size: int = 100,
        archive_limit_mb: Callable[[], float] | None = None,
    ):
        if (
            min(
                max_pending_count, max_pending_bytes, max_recent_count, max_recent_bytes
            )
            <= 0
        ):
            raise ValueError("截图数量和字节数上限必须大于 0")
        if cleanup_interval <= 0:
            raise ValueError("截图清理间隔必须大于 0")
        self.folder = Path(folder)
        self.retention_hours = retention_hours
        self.logger = logger or logging.getLogger(__name__)
        self.cleanup_interval = cleanup_interval
        self.max_pending_count = max_pending_count
        self.max_pending_bytes = max_pending_bytes
        self.max_recent_count = max_recent_count
        self.max_recent_bytes = max_recent_bytes
        self.archive_limit_mb = archive_limit_mb or (lambda: 5120)
        self._archive_bytes: int | None = None
        self._last_archive_limit_log = float("-inf")
        self._recent_frames: deque[Screenshot] = deque()
        self._recent_bytes = 0
        self._deleted_archives: set[str] = set()
        self._encoder = encoder
        self._write_frame = writer
        self._clock = clock or (lambda: time.monotonic())
        self._wall_time_ns = wall_time_ns or (lambda: time.time_ns())
        self._cleanup = ScreenshotCleanup(
            self.folder,
            retention_hours,
            time_ns=self._wall_time_ns,
            batch_size=cleanup_batch_size,
        )
        self._cleanup_scanned = 0
        self._cleanup_deleted = 0
        self._cleanup_batches = 0
        self._cleanup_complete = True
        self._active: Screenshot | None = None
        self._capture_ms = 0.0
        self._encode_ms = 0.0
        self._preview_encode_ms = 0.0
        self._encode_failed = 0
        self._preview_failed = 0
        self._latest_persisted_at: float | None = None
        self._preview_pending: Screenshot | None = None
        self._preview_active: Screenshot | None = None
        self._preview_replaced = 0
        self._shutdown_dropped = 0
        self._shutdown_preview_dropped = 0
        self._shutdown_archive_dropped = 0
        self._archive_dropped = 0
        self._queue: deque[Screenshot] = deque()
        self._lock = Lock()
        self._ready = Condition(self._lock)
        self._cleanup_lock = Lock()
        self._archive_lock = Lock()
        self._stop = Event()
        self._flush_deadline: float | None = None
        self._threads: list[Thread] = []
        self._latest: Screenshot | None = None
        self._last_saved = ""
        self._last_timestamp = 0
        self._pending_count = 0
        self._pending_bytes = 0
        self._saved = 0
        self._failed = 0
        self._dropped = 0
        self._dropped_bytes = 0
        self._dropped_important = 0
        self._reported_dropped = 0
        self._last_drop_log = float("-inf")
        self._write_ms = 0.0
        self._queue_wait_ms = 0.0
        self._cleanup_ms = 0.0
        self._cleanup_failed = 0
        self._last_error_log = float("-inf")
        self._last_reported_state = (0,) * len(_STATUS_FIELDS)
        self._error_windows: list[tuple[int, int, str]] = []
        self._archive_queue: deque[
            tuple[int, int, str, str, int, deque[Screenshot]]
        ] = deque()
        self._log_archive_queue: list[tuple[int, str]] = []

    def start(self):
        with self._lock:
            if self._threads or self._stop.is_set():
                return
            self._recover_error_windows()
            for name, target in (
                ("screenshot-preview", self._preview_encoder),
                ("screenshot-writer", self._writer),
                ("screenshot-cleaner", self._cleaner),
                ("screenshot-archiver", self._archiver),
            ):
                thread = Thread(name=name, target=target, daemon=True)
                self._threads.append(thread)
                thread.start()

    def _recover_error_windows(self):
        """重启后继续归档尚未结束的报错窗口。调用时持有 _lock。"""
        root = self.folder / "errors"
        if not root.exists():
            return
        now = self._wall_time_ns()
        with os.scandir(root) as entries:
            for entry in entries:
                if self._stop.is_set():
                    return
                if not entry.is_dir(follow_symlinks=False) or not entry.name.isdigit():
                    continue
                folder = Path(entry.path)
                try:
                    with (folder / "event.json").open(encoding="utf-8") as source:
                        event = json.loads(source.read(16384))
                    timestamp = int(event["time_ns"])
                    last_error = int(event.get("last_error_ns", timestamp))
                except (OSError, ValueError, KeyError, TypeError):
                    continue
                if last_error < now - _LOG_RETENTION_NS:
                    continue
                if last_error + 2 * _ERROR_WINDOW_NS >= now:
                    self._error_windows.append(
                        (
                            timestamp - _ERROR_WINDOW_NS,
                            last_error + _ERROR_WINDOW_NS,
                            folder.name,
                        )
                    )
                    self._archive_queue.append(
                        (
                            timestamp - _ERROR_WINDOW_NS,
                            last_error,
                            folder.name,
                            event.get("message", "运行出错"),
                            0,
                            deque(),
                        )
                    )
                if not (folder / "logs.json").exists():
                    heapq.heappush(
                        self._log_archive_queue,
                        (
                            max(now, last_error + _ERROR_WINDOW_NS + 5 * 10**9),
                            folder.name,
                        ),
                    )

    def close(self, timeout=5):
        """Drain history until the deadline, then discard waiting work.

        In-flight native encoding or OS writes cannot be killed by Python.
        Report any still-running daemon worker; it exits once that call returns.
        A subsequent close can join it, but never reopens admission.
        """
        # Shutdown uses real time even when metric clocks are frozen in tests.
        deadline = time.monotonic() + max(0, timeout)
        with self._ready:
            if not self._stop.is_set():
                self._flush_deadline = deadline
                self._stop.set()
                self._shutdown_preview_dropped += int(self._preview_pending is not None)
                self._preview_pending = None
                # 唤醒空闲写盘线程；不向已满队列插入退出标记。
                self._ready.notify_all()
        for thread in self._threads:
            thread.join(max(0, deadline - time.monotonic()))
        # A manual cleanup may still be in an OS call. Do not wait on its lock.
        if self._cleanup_lock.acquire(blocking=False):
            try:
                self._cleanup.close()
            finally:
                self._cleanup_lock.release()
        with self._lock:
            self._flush_deadline = min(self._flush_deadline, time.monotonic())
            self._recent_frames.clear()
            self._recent_bytes = 0
            self._shutdown_archive_dropped += len(self._archive_queue) + len(
                self._log_archive_queue
            )
            self._archive_queue.clear()
            self._log_archive_queue.clear()
            self._error_windows.clear()
            self._shutdown_dropped += len(self._queue)
            for frame in self._queue:
                self._release_pending(frame)
            self._queue.clear()
            self._ready.notify_all()
            remaining = [thread.name for thread in self._threads if thread.is_alive()]
        result = {"remaining_threads": remaining, **self.stats()}
        if (
            remaining
            or result["shutdown_dropped"]
            or result["shutdown_archive_dropped"]
        ):
            self.logger.warning("截图关闭状态 %s", result)
        return result

    def _flush_expired(self):
        return (
            self._flush_deadline is not None
            and time.monotonic() >= self._flush_deadline
        )

    def submit(self, img, sub_folder=None) -> str:
        # cv2.imencode 返回可变 ndarray；只复制编码数据，不复制识别用的整帧。
        size = img.nbytes if isinstance(img, np.ndarray) else len(img)
        if size > 1920 * 1080 * 4:
            raise ValueError("JPEG 截图超过单帧上限")
        return self._submit(bytes(img), sub_folder)

    def submit_frame(self, img, sub_folder=None, *, capture_ms=None) -> str:
        """Copy a bounded RGB/gray snapshot; never run encoding or disk I/O here."""
        if (
            not isinstance(img, np.ndarray)
            or img.dtype != np.uint8
            or img.ndim not in (2, 3)
            or (img.ndim == 3 and img.shape[2] != 3)
            or not 0 < img.nbytes <= 1920 * 1080 * 3
        ):
            raise ValueError("截图必须是最多 1920×1080 像素的 uint8 RGB 或灰度帧")
        return self._submit(img, sub_folder, capture_ms=capture_ms)

    def _submit(self, data, sub_folder, *, capture_ms=None):
        if sub_folder and (
            Path(sub_folder).name != sub_folder
            or sub_folder in {".", ".."}
            or "\\" in sub_folder
        ):
            raise ValueError("截图子目录必须是单个目录名")
        with self._lock:
            if self._stop.is_set():
                raise RuntimeError("截图存储已关闭")
            if isinstance(data, np.ndarray):
                # Copy under the admission lock so concurrent producers cannot
                # allocate an unbounded number of pending snapshots.
                data = data.copy()
                data.flags.writeable = False
            if capture_ms is not None:
                self._capture_ms = capture_ms
            captured_ns = max(self._wall_time_ns(), self._last_timestamp + 1)
            self._last_timestamp = captured_ns
            folder = sub_folder or datetime.fromtimestamp(captured_ns / 10**9).strftime(
                "%Y%m%d-%H"
            )
            filename = f"{folder}/{captured_ns}.jpg"
            frame = Screenshot(
                filename,
                data,
                captured_ns,
                self._clock(),
                not sub_folder,
                sub_folder in IMPORTANT_FOLDERS,
            )
            if frame.preview:
                if isinstance(data, bytes):
                    if _newer_than(self._latest, frame):
                        self._latest = frame
                    if self._preview_pending is not None:
                        self._preview_replaced += 1
                        self._preview_pending = None
                else:
                    if self._preview_pending is not None:
                        self._preview_replaced += 1
                    self._preview_pending = frame
                    self._ready.notify_all()
            save_history = self.retention_hours() > 0
            if save_history:
                self._recent_frames.clear()
                self._recent_bytes = 0
            elif isinstance(data, bytes):
                self._remember_frame(frame)
            # Raw snapshots share the bounded writer queue even when their
            # destination is only the encoded pre-error memory cache.
            persist = (
                save_history
                or isinstance(data, np.ndarray)
                or self._in_error_window(captured_ns)
            )
            if persist and self._make_room(frame):
                self._pending_count += 1
                self._pending_bytes += frame.size
                frame._pending_bytes = frame.size
                self._queue.append(frame)
                self._ready.notify_all()
        self._report_dropped()
        return filename

    def _remember_frame(self, frame):
        """Retain encoded frames in capture order. The caller holds _lock."""
        if self._flush_expired():
            return
        frames = [
            recent
            for recent in self._recent_frames
            if recent.captured_ns != frame.captured_ns
        ]
        frames.append(frame)
        self._recent_frames = deque(sorted(frames, key=lambda item: item.captured_ns))
        self._recent_bytes = sum(recent.size for recent in self._recent_frames)
        while self._recent_frames and (
            self._last_timestamp - self._recent_frames[0].captured_ns > _ERROR_WINDOW_NS
            or len(self._recent_frames) > self.max_recent_count
            or self._recent_bytes > self.max_recent_bytes
        ):
            self._recent_bytes -= self._recent_frames.popleft().size

    def _preview_encoder(self):
        while True:
            with self._ready:
                self._ready.wait_for(
                    lambda: self._preview_pending is not None or self._stop.is_set()
                )
                if self._stop.is_set():
                    self._preview_pending = None
                    return
                frame = self._preview_active = self._preview_pending
                self._preview_pending = None
            try:
                self._encode(frame, preview=True)
            except Exception as exc:
                with self._lock:
                    self._preview_failed += 1
                self._report_error("截图预览编码失败", exc)
            finally:
                with self._lock:
                    self._preview_active = None
                del frame

    def _encode(self, frame, *, preview=False):
        with self._ready:
            while frame._encoding:
                # The owner publishes this frame. Preview stays available for
                # a newer slot instead of waiting for another worker's encoder.
                if preview or self._flush_expired():
                    return None
                remaining = (
                    None
                    if self._flush_deadline is None
                    else max(0, self._flush_deadline - time.monotonic())
                )
                self._ready.wait(timeout=remaining)
            if frame._encode_error is not None:
                raise RuntimeError(frame._encode_error)
            if isinstance(frame.data, bytes):
                return frame
            if self._flush_expired():
                return None
            frame._encoding = True
            raw = frame.data
        started = self._clock()
        data = b""
        error = None
        try:
            data = bytes(self._encoder(raw))
            if not data or len(data) > 1920 * 1080 * 4:
                raise ValueError("JPEG 编码结果为空或超过单帧上限")
        except Exception as exc:
            # Retaining the exception would also retain the encoder's RGB
            # argument through its traceback, including in asynchronous logs.
            error = str(exc)
            data = b""
        finally:
            del raw
        with self._ready:
            if frame._pending_bytes is not None:
                if self._flush_expired():
                    if frame is not self._active:
                        self._queue.remove(frame)
                    self._release_pending(frame)
                    self._shutdown_dropped += 1
                elif not self._make_room(frame, size=len(data)):
                    if frame is not self._active:
                        self._queue.remove(frame)
                    self._release_pending(frame)
                else:
                    self._pending_bytes += len(data) - frame._pending_bytes
                    frame._pending_bytes = len(data)
            frame.data = data
            frame._encode_error = error
            frame._encoding = False
            elapsed = (self._clock() - started) * 1000
            if preview:
                self._preview_encode_ms = elapsed
            else:
                self._encode_ms = elapsed
            if error is not None:
                self._encode_failed += 1
            elif (
                frame.preview
                and not self._stop.is_set()
                and _newer_than(self._latest, frame)
            ):
                self._latest = frame
            self._ready.notify_all()
        # Raise outside the encoder's except block so the new exception has no
        # __context__ pointing back to the released RGB array.
        if error is not None:
            raise RuntimeError(error)
        return frame

    def _release_pending(self, frame):
        """Release an admitted history charge once. The caller holds _lock."""
        if frame._pending_bytes is not None:
            self._pending_count -= 1
            self._pending_bytes -= frame._pending_bytes
            frame._pending_bytes = None

    def _record_drop(self, frame: Screenshot, *, size=None):
        self._dropped += 1
        self._dropped_bytes += frame.size if size is None else size
        self._dropped_important += int(frame.important)

    def _make_room(self, frame: Screenshot, *, size=None) -> bool:
        # 调用时持有 _lock，容量同时计入等待中和正在写入的截图。
        incoming_size = frame.size if size is None else size
        count = self._pending_count + int(frame._pending_bytes is None)
        size = self._pending_bytes + incoming_size - (frame._pending_bytes or 0)

        def fits():
            return count <= self.max_pending_count and size <= self.max_pending_bytes

        if fits():
            return True
        evicted = []
        if incoming_size <= self.max_pending_bytes:
            for waiting in self._queue:
                if (
                    waiting is frame
                    or waiting.important
                    or any(
                        start <= waiting.captured_ns <= end
                        for start, end, _ in self._error_windows
                    )
                ):
                    continue
                evicted.append(waiting)
                count -= 1
                size -= waiting.size
                if fits():
                    break
        if not fits():
            # 已在写入的图、关键截图不能淘汰；保持原队列，跳过新图。
            self._record_drop(frame, size=incoming_size)
            return False
        for waiting in evicted:
            self._queue.remove(waiting)
            self._release_pending(waiting)
            self._record_drop(waiting)
        return True

    def _report_dropped(self):
        now = time.monotonic()
        with self._lock:
            if (
                self._dropped == self._reported_dropped
                or now - self._last_drop_log < 30
            ):
                return
            self._reported_dropped = self._dropped
            self._last_drop_log = now
            dropped = self._dropped
            important = self._dropped_important
        self.logger.warning(
            "截图待写容量不足，累计跳过 %s 张（关键截图 %s 张），内存预览继续更新",
            dropped,
            important,
        )

    def latest(self) -> Screenshot | None:
        with self._lock:
            return self._latest

    def _in_error_window(self, captured_ns: int) -> bool:
        """调用时持有 _lock。关闭通常保存时只入队必要画面。"""
        return any(
            int(archive_id) <= captured_ns <= end
            for _, end, archive_id in self._error_windows
        )

    def mark_error(self, timestamp_ns: int, message: str) -> str:
        """同一截图窗口内的错误合并归档，并延长至末次报错后五分钟。"""
        with self._ready:
            if self._stop.is_set():
                return str(timestamp_ns)
            self._error_windows = [
                window
                for window in self._error_windows
                if window[1] >= timestamp_ns - _ERROR_WINDOW_NS
            ]
            existing = next(
                (
                    window
                    for window in reversed(self._error_windows)
                    if int(window[2]) <= timestamp_ns
                    and window[1] >= timestamp_ns - _ERROR_WINDOW_NS
                    and window[2] not in self._deleted_archives
                ),
                None,
            )
            if existing is None:
                archive_id = str(timestamp_ns)
                scan_start = timestamp_ns - _ERROR_WINDOW_NS
                if (
                    max(
                        len(self._error_windows),
                        len(self._archive_queue),
                        len(self._log_archive_queue),
                    )
                    >= self.max_pending_count
                ):
                    self._archive_dropped += 1
                    return archive_id
                self._error_windows.append(
                    (scan_start, timestamp_ns + _ERROR_WINDOW_NS, archive_id)
                )
            else:
                start, old_end, archive_id = existing
                if len(self._archive_queue) >= self.max_pending_count:
                    self._archive_dropped += 1
                    return archive_id
                scan_start = max(old_end + 1, timestamp_ns - _ERROR_WINDOW_NS)
                self._error_windows.remove(existing)
                self._error_windows.append(
                    (start, max(old_end, timestamp_ns + _ERROR_WINDOW_NS), archive_id)
                )
                self._log_archive_queue = [
                    item for item in self._log_archive_queue if item[1] != archive_id
                ]
                heapq.heapify(self._log_archive_queue)
            buffered = deque()
            if self.retention_hours() <= 0:
                before = [
                    frame
                    for frame in self._recent_frames
                    if scan_start <= frame.captured_ns <= timestamp_ns
                ]
                after = [
                    frame
                    for frame in self._recent_frames
                    if timestamp_ns
                    < frame.captured_ns
                    <= timestamp_ns + _ERROR_WINDOW_NS
                ]
                buffered = deque((*before, *after))
            self._archive_queue.append(
                (scan_start, timestamp_ns, archive_id, message[:4096], 1, buffered)
            )
            heapq.heappush(
                self._log_archive_queue,
                (timestamp_ns + _ERROR_WINDOW_NS + 5 * 10**9, archive_id),
            )
            self._ready.notify_all()
        return archive_id

    def delete_error_archive(self, archive_id: str) -> bool:
        """删除单条报错归档，并阻止进行中的后台写入重建它。"""
        with self._archive_lock:
            return self._delete_error_archive_locked(archive_id)

    def _delete_error_archive_locked(
        self, archive_id: str, *, require_manifest: bool = True
    ) -> bool:
        destination = self.folder / "errors" / archive_id
        if not destination.is_dir() or (
            require_manifest and not (destination / "event.json").is_file()
        ):
            return False
        size = self._archive_size(destination) if self._archive_bytes is not None else 0
        self._deleted_archives.add(archive_id)
        try:
            shutil.rmtree(destination)
            if self._archive_bytes is not None:
                self._archive_bytes = max(0, self._archive_bytes - size)
        finally:
            with self._ready:
                self._error_windows = [
                    window for window in self._error_windows if window[2] != archive_id
                ]
                self._archive_queue = deque(
                    item for item in self._archive_queue if item[2] != archive_id
                )
                self._log_archive_queue = [
                    item for item in self._log_archive_queue if item[1] != archive_id
                ]
                heapq.heapify(self._log_archive_queue)
                self._ready.notify_all()
        return True

    @staticmethod
    def _archive_size(folder: Path) -> int:
        try:
            with os.scandir(folder) as entries:
                return sum(
                    entry.stat(follow_symlinks=False).st_size
                    for entry in entries
                    if entry.is_file(follow_symlinks=False)
                )
        except FileNotFoundError:
            return 0

    def _archive_candidates_locked(self):
        root = self.folder / "errors"
        if not root.exists():
            return []
        candidates = []
        with os.scandir(root) as entries:
            for entry in entries:
                if (
                    not entry.is_dir(follow_symlinks=False)
                    or not entry.name.isascii()
                    or not entry.name.isdigit()
                ):
                    continue
                try:
                    event = json.loads(
                        (Path(entry.path) / "event.json").read_text(encoding="utf-8")
                    )
                    last_error = int(event.get("last_error_ns", entry.name))
                except (OSError, ValueError, TypeError, AttributeError):
                    last_error = int(entry.name)
                candidates.append((last_error, int(entry.name), entry.name))
        return sorted(candidates)

    def _archive_usage_locked(self) -> int:
        if self._archive_bytes is None:
            self._archive_bytes = sum(
                self._archive_size(self.folder / "errors" / archive_id)
                for _, _, archive_id in self._archive_candidates_locked()
            )
        return self._archive_bytes

    def _ensure_archive_capacity_locked(self, additional: int, protected_id: str):
        limit = self.archive_limit_mb() * 1024**2
        if limit == 0:
            return True
        if additional > limit:
            return False
        if self._archive_usage_locked() + additional <= limit:
            return True
        for _, _, archive_id in self._archive_candidates_locked():
            if archive_id == protected_id:
                continue
            self._delete_error_archive_locked(archive_id, require_manifest=False)
            if self._archive_bytes + additional <= limit:
                return True
        return False

    def _archive_limit_warning(self):
        now = time.monotonic()
        if now - self._last_archive_limit_log >= 30:
            self._last_archive_limit_log = now
            self.logger.warning("报错归档已达磁盘上限，部分新截图或日志未保存")

    def _archive_frame(self, frame: Screenshot) -> bool:
        if self._flush_expired():
            return False
        if isinstance(frame.data, np.ndarray):
            frame = self._encode(frame)
            if frame is None:
                return False
        with self._lock:
            self._error_windows = [
                window
                for window in self._error_windows
                if window[1] >= frame.captured_ns - _ERROR_WINDOW_NS
            ]
            windows = tuple(self._error_windows)
        archived = False
        for start, end, archive_id in windows:
            if start <= frame.captured_ns <= end:
                destination = (
                    self.folder / "errors" / archive_id / Path(frame.filename).name
                )
                try:
                    with self._archive_lock:
                        if (
                            self._flush_expired()
                            or archive_id in self._deleted_archives
                        ):
                            continue
                        if destination.exists():
                            archived = True
                            continue
                        if not self._ensure_archive_capacity_locked(
                            frame.size, archive_id
                        ):
                            self._archive_limit_warning()
                            continue
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        temporary = destination.with_suffix(".jpg.tmp")
                        try:
                            if self._flush_expired():
                                return archived
                            temporary.write_bytes(frame.data)
                            os.replace(temporary, destination)
                            if self._archive_bytes is not None:
                                self._archive_bytes += frame.size
                            archived = True
                        finally:
                            temporary.unlink(missing_ok=True)
                except OSError as exc:
                    self._report_error("归档报错截图失败", exc)
        return archived

    def _copy_to_archive(self, source: Path, destination: Path):
        with self._archive_lock:
            if (
                self._flush_expired()
                or destination.parent.name in self._deleted_archives
            ):
                return
            if destination.exists():
                return
            size = source.stat().st_size
            if not self._ensure_archive_capacity_locked(size, destination.parent.name):
                self._archive_limit_warning()
                return
            temporary = destination.with_suffix(".jpg.tmp")
            try:
                if self._flush_expired():
                    return
                shutil.copy2(source, temporary)
                os.replace(temporary, destination)
                if self._archive_bytes is not None:
                    self._archive_bytes += size
            finally:
                temporary.unlink(missing_ok=True)

    def _archiver(self):
        while True:
            with self._ready:
                while True:
                    if self._flush_expired():
                        return
                    if self._archive_queue:
                        start, end, archive_id, message, increment, buffered = (
                            self._archive_queue.popleft()
                        )
                        deadline = None
                        break
                    remaining = None
                    if self._log_archive_queue:
                        deadline, archive_id = self._log_archive_queue[0]
                        remaining = (deadline - time.time_ns()) / 10**9
                        if remaining <= 0:
                            heapq.heappop(self._log_archive_queue)
                            break
                    if self._stop.is_set():
                        # A future snapshot must still cover the complete error
                        # window. Its manifest schedules it again after restart.
                        return
                    self._ready.wait(timeout=remaining)
            if deadline is not None:
                self._save_error_logs(archive_id)
                continue
            destination = self.folder / "errors" / archive_id
            try:
                with self._archive_lock:
                    if self._flush_expired():
                        with self._lock:
                            self._shutdown_archive_dropped += 1
                        continue
                    if archive_id in self._deleted_archives:
                        continue
                    destination.mkdir(parents=True, exist_ok=True)
                    manifest = destination / "event.json"
                    exists = manifest.exists()
                    if exists:
                        event = json.loads(manifest.read_text(encoding="utf-8"))
                    elif increment:
                        event = {"time_ns": int(archive_id), "message": message}
                    else:
                        continue
                    if increment:
                        event["error_count"] = (
                            int(event.get("error_count", 1 if exists else 0)) + 1
                        )
                        event["last_error_ns"] = max(
                            int(event.get("last_error_ns", event["time_ns"])), end
                        )
                    if increment and exists:
                        old_logs = destination / "logs.json"
                        if old_logs.exists():
                            old_size = old_logs.stat().st_size
                            old_logs.unlink()
                            if self._archive_bytes is not None:
                                self._archive_bytes -= old_size
                    contents = json.dumps(event, ensure_ascii=False).encode("utf-8")
                    previous_size = manifest.stat().st_size if exists else 0
                    if not self._ensure_archive_capacity_locked(
                        max(0, len(contents) - previous_size), archive_id
                    ):
                        self._archive_limit_warning()
                        if not exists:
                            self._delete_error_archive_locked(
                                archive_id, require_manifest=False
                            )
                        continue
                    temporary = destination / "event.json.tmp"
                    try:
                        if self._flush_expired():
                            with self._lock:
                                self._shutdown_archive_dropped += 1
                            continue
                        temporary.write_bytes(contents)
                        os.replace(temporary, manifest)
                        if self._archive_bytes is not None:
                            self._archive_bytes += len(contents) - previous_size
                    finally:
                        temporary.unlink(missing_ok=True)
                while buffered:
                    if self._flush_expired():
                        with self._lock:
                            self._shutdown_archive_dropped += 1
                        return
                    self._archive_frame(buffered.popleft())
                scan_end = min(end + _ERROR_WINDOW_NS, time.time_ns())
                if start > scan_end:
                    continue
                hour = datetime.fromtimestamp(start / 10**9).replace(
                    minute=0, second=0, microsecond=0
                )
                last_hour = datetime.fromtimestamp(scan_end / 10**9)
                hour_folders = set()
                while hour <= last_hour:
                    hour_folders.add(hour.strftime("%Y%m%d-%H"))
                    hour += timedelta(hours=1)
                for folder in self.folder.iterdir():
                    if self._flush_expired():
                        return
                    if not folder.is_dir() or folder.name == "errors":
                        continue
                    if (
                        HOUR_FOLDER.fullmatch(folder.name)
                        and folder.name not in hour_folders
                    ):
                        continue
                    for timestamp, name in self._images(folder):
                        if start <= timestamp <= scan_end:
                            try:
                                self._copy_to_archive(folder / name, destination / name)
                            except FileNotFoundError:
                                continue
                for timestamp, name in self._images(self.folder):
                    if start <= timestamp <= scan_end:
                        try:
                            self._copy_to_archive(
                                self.folder / name, destination / name
                            )
                        except FileNotFoundError:
                            continue
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                self._report_error("归档报错截图失败", exc)

    def _save_error_logs(self, archive_id: str):
        from arknights_mower.utils.diagnostics import timeline

        destination = self.folder / "errors" / archive_id
        try:
            event = json.loads((destination / "event.json").read_text(encoding="utf-8"))
            timestamp = int(event["time_ns"])
            last_error = int(event.get("last_error_ns", timestamp))
            center = datetime.fromtimestamp(timestamp / 10**9)
            rows = timeline(
                self.folder.parent / "log",
                destination,
                center,
                limit=None,
                start=datetime.fromtimestamp((timestamp - _ERROR_WINDOW_NS) / 10**9),
                end=datetime.fromtimestamp((last_error + _ERROR_WINDOW_NS) / 10**9),
            )
            for row in rows:
                if row["screenshot"]:
                    row["screenshot"] = f"errors/{archive_id}/{row['screenshot']}"
            contents = json.dumps(rows, ensure_ascii=False).encode("utf-8")
            with self._archive_lock:
                if self._flush_expired():
                    with self._lock:
                        self._shutdown_archive_dropped += 1
                    return
                if archive_id in self._deleted_archives:
                    return
                saved = destination / "logs.json"
                previous_size = saved.stat().st_size if saved.exists() else 0
                if not self._ensure_archive_capacity_locked(
                    max(0, len(contents) - previous_size), archive_id
                ):
                    self._archive_limit_warning()
                    return
                temporary = destination / "logs.json.tmp"
                try:
                    if self._flush_expired():
                        with self._lock:
                            self._shutdown_archive_dropped += 1
                        return
                    temporary.write_bytes(contents)
                    os.replace(temporary, saved)
                    if self._archive_bytes is not None:
                        self._archive_bytes += len(contents) - previous_size
                finally:
                    temporary.unlink(missing_ok=True)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            self._report_error("归档报错日志失败", exc)

    def last_saved(self) -> str:
        with self._lock:
            return self._last_saved

    def stats(self) -> dict:
        with self._lock:
            now = self._clock()
            pending = list(self._queue)
            if self._active is not None and self._active._pending_bytes is not None:
                pending.append(self._active)
            raw = [frame for frame in pending if isinstance(frame.data, np.ndarray)]
            return {
                # 包含正在写入的一帧，因此慢磁盘下也能观察真实待写占用。
                "pending_count": self._pending_count,
                "preview_pending_count": int(self._preview_pending is not None),
                "preview_replaced": self._preview_replaced,
                "shutdown_dropped": self._shutdown_dropped,
                "shutdown_preview_dropped": self._shutdown_preview_dropped,
                "shutdown_archive_dropped": self._shutdown_archive_dropped,
                "archive_pending_count": len(self._archive_queue),
                "archive_log_pending_count": len(self._log_archive_queue),
                "archive_window_count": len(self._error_windows),
                "archive_dropped": self._archive_dropped,
                "preview_active_count": int(self._preview_active is not None),
                "preview_pending_bytes": (
                    self._preview_pending.size if self._preview_pending else 0
                ),
                "preview_active_bytes": (
                    self._preview_active.size if self._preview_active else 0
                ),
                "oldest_preview_pending_age": max(
                    (
                        max(0, now - frame.queued_at)
                        for frame in (self._preview_pending, self._preview_active)
                        if frame is not None
                    ),
                    default=0,
                ),
                "raw_pending_count": len(raw),
                "raw_pending_bytes": sum(frame.size for frame in raw),
                "oldest_pending_age": max(
                    (max(0, now - frame.queued_at) for frame in pending), default=0
                ),
                "preview_age": (
                    max(0, now - self._latest.queued_at) if self._latest else None
                ),
                "latest_persisted_age": (
                    max(0, now - self._latest_persisted_at)
                    if self._latest_persisted_at is not None
                    else None
                ),
                "capture_ms": round(self._capture_ms, 2),
                "encode_ms": round(self._encode_ms, 2),
                "preview_encode_ms": round(self._preview_encode_ms, 2),
                "encode_failed": self._encode_failed,
                "preview_failed": self._preview_failed,
                "pending_bytes": self._pending_bytes,
                "max_pending_count": self.max_pending_count,
                "max_pending_bytes": self.max_pending_bytes,
                "saved": self._saved,
                "failed": self._failed,
                "dropped": self._dropped,
                "dropped_bytes": self._dropped_bytes,
                "dropped_important": self._dropped_important,
                "write_ms": round(self._write_ms, 2),
                "queue_wait_ms": round(self._queue_wait_ms, 2),
                "cleanup_ms": round(self._cleanup_ms, 2),
                "cleanup_scanned": self._cleanup_scanned,
                "cleanup_deleted": self._cleanup_deleted,
                "cleanup_batches": self._cleanup_batches,
                "cleanup_complete": self._cleanup_complete,
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
                    if self._flush_expired():
                        return False
                    with temporary.open("wb") as output:
                        if self._flush_expired():
                            return False
                        output.write(frame.data)
                    break
                except FileNotFoundError:
                    # 清理线程可能刚删除了这个空目录，重建后再试一次。
                    if attempt:
                        raise
            os.replace(temporary, destination)
            return True
        finally:
            temporary.unlink(missing_ok=True)

    def _writer(self):
        while True:
            with self._ready:
                self._ready.wait_for(lambda: self._queue or self._stop.is_set())
                if not self._queue or self._flush_expired():
                    return
                frame = self._active = self._queue.popleft()
            try:
                started = self._clock()
                write_started = None
                write_enabled = False
                try:
                    save_history = self.retention_hours() > 0
                    encoded = self._encode(frame)
                    try:
                        if encoded is None:
                            with self._lock:
                                if frame._pending_bytes is not None:
                                    self._shutdown_dropped += 1
                            continue
                        if frame._pending_bytes is None:
                            continue
                        if self._flush_expired():
                            with self._lock:
                                self._shutdown_dropped += 1
                            continue
                        if save_history:
                            write_started = self._clock()
                            if (self._write_frame or self._write)(encoded) is False:
                                with self._lock:
                                    self._shutdown_dropped += 1
                                continue
                            self._archive_frame(encoded)
                            write_enabled = True
                        else:
                            with self._lock:
                                self._remember_frame(encoded)
                            if not self._archive_frame(encoded):
                                if self._flush_expired():
                                    with self._lock:
                                        self._shutdown_dropped += 1
                                continue
                            write_enabled = True
                    finally:
                        del encoded
                except Exception as exc:
                    with self._lock:
                        self._failed += 1
                    self._report_error(f"截图写入失败 {frame.filename}", exc)
                else:
                    with self._lock:
                        self._saved += 1
                        if write_enabled:
                            self._latest_persisted_at = frame.queued_at
                        if frame.preview and self.retention_hours() > 0:
                            self._last_saved = frame.filename
                finally:
                    with self._lock:
                        self._release_pending(frame)
                        self._active = None
                        if write_enabled:
                            self._queue_wait_ms = (started - frame.queued_at) * 1000
                        if write_started is not None:
                            self._write_ms = (self._clock() - write_started) * 1000
            finally:
                del frame

    # Diagnostics also reads legacy second-resolution filenames.
    _timestamp = staticmethod(screenshot_timestamp)

    def _images(self, folder):
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if self._flush_expired():
                        return
                    if entry.is_file(follow_symlinks=False):
                        timestamp = self._timestamp(entry.name)
                        if timestamp is not None:
                            yield timestamp, entry.name
        except FileNotFoundError:
            return

    def _cleanup_error(self, exc):
        with self._lock:
            self._cleanup_failed += 1
        self._report_error("清理截图失败", exc)

    def _clean_error_archives(self):
        with self._archive_lock:
            limit = self.archive_limit_mb() * 1024**2
            cutoff = self._wall_time_ns() - _LOG_RETENTION_NS
            # 定期重新扫描，兼容程序外部增删归档文件以及运行中修改上限。
            candidates = self._archive_candidates_locked()
            self._archive_bytes = sum(
                self._archive_size(self.folder / "errors" / archive_id)
                for _, _, archive_id in candidates
            )
            for last_error, _, archive_id in candidates:
                if self._stop.is_set():
                    break
                if last_error < cutoff or (limit > 0 and self._archive_bytes > limit):
                    self._delete_error_archive_locked(
                        archive_id, require_manifest=False
                    )

    def cleanup(self):
        """Run one bounded batch, independently of preview and admission."""
        with self._cleanup_lock:
            started = self._clock()
            result = {"scanned": 0, "deleted": 0, "complete": True, "errors": ()}
            try:
                if not self._stop.is_set():
                    result = self._cleanup.step()
                for error in result["errors"]:
                    self._cleanup_error(error)
                self._clean_error_archives()
            except Exception as exc:
                self._cleanup_error(exc)
            finally:
                if self._stop.is_set():
                    self._cleanup.close()
                with self._lock:
                    self._cleanup_ms = (self._clock() - started) * 1000
                    self._cleanup_scanned += result["scanned"]
                    self._cleanup_deleted += result["deleted"]
                    self._cleanup_batches += 1
                    self._cleanup_complete = result["complete"]
            return result

    def _report_status(self):
        stats = self.stats()
        state = tuple(stats[field] for field in _STATUS_FIELDS)
        # 清理耗时自然波动不代表截图活动，空闲时不重复打印全零统计。
        if stats["pending_count"] or state != self._last_reported_state:
            self.logger.debug("截图存储状态 %s", stats)
        self._last_reported_state = state

    def _cleaner(self):
        last_cleanup = float("-inf")
        last_report = float("-inf")
        last_archive_limit = None
        poll_interval = min(30, self.cleanup_interval)
        try:
            while not self._stop.is_set():
                archive_limit = self.archive_limit_mb()
                if (
                    not self._cleanup_complete
                    or self._clock() - last_cleanup >= self.cleanup_interval
                    or archive_limit != last_archive_limit
                ):
                    self.cleanup()
                    if self._cleanup_complete:
                        last_cleanup = self._clock()
                        last_archive_limit = archive_limit
                if self._clock() - last_report >= poll_interval:
                    self._report_status()
                    last_report = self._clock()
                if self._stop.wait(poll_interval if self._cleanup_complete else 0.01):
                    return
        finally:
            with self._cleanup_lock:
                self._cleanup.close()
