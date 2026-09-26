"""截图的内存预览、后台存储和独立过期清理。

识别端只提交已经编码的图片，不等待磁盘。待写数量和字节数均有上限，
积压时优先淘汰普通截图，并记录跳过数量及存储耗时。
"""

import heapq
import json
import logging
import os
import re
import shutil
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from threading import Condition, Event, Lock, Thread
from typing import Callable

from arknights_mower.utils.log_retention import RUNTIME_LOG_RETENTION_HOURS

_HOUR_FOLDER = re.compile(r"\d{8}-\d{2}\Z")
_IMPORTANT_FOLDERS = {"run_order", "workshop", "furniture", "solve_captcha"}
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
)


@dataclass(frozen=True)
class Screenshot:
    filename: str
    data: bytes
    captured_ns: int
    queued_at: float
    preview: bool
    important: bool


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
        archive_limit_mb: Callable[[], int] | None = None,
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
        self._queue: deque[Screenshot] = deque()
        self._lock = Lock()
        self._ready = Condition(self._lock)
        self._cleanup_lock = Lock()
        self._archive_lock = Lock()
        self._stop = Event()
        self._threads: list[Thread] = []
        self._latest: Screenshot | None = None
        self._recent_frames: deque[Screenshot] = deque()
        self._recent_bytes = 0
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
        self._deleted_archives: set[str] = set()

    def start(self):
        with self._lock:
            if self._threads:
                return
            self._recover_error_windows()
            for name, target in (
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
        now = time.time_ns()
        for folder in root.iterdir():
            if not folder.is_dir() or not folder.name.isdigit():
                continue
            try:
                event = json.loads((folder / "event.json").read_text(encoding="utf-8"))
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
                    (max(now, last_error + _ERROR_WINDOW_NS + 5 * 10**9), folder.name),
                )

    def close(self, timeout=5):
        """正常关闭时排空写盘队列；磁盘卡住时不无限等待。"""
        with self._ready:
            if not self._stop.is_set():
                self._stop.set()
                # 唤醒空闲写盘线程；不向已满队列插入退出标记。
                self._ready.notify_all()
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
                filename,
                data,
                captured_ns,
                time.monotonic(),
                not sub_folder,
                sub_folder in _IMPORTANT_FOLDERS,
            )
            if frame.preview:
                self._latest = frame
            save_history = self.retention_hours() > 0
            if save_history:
                self._recent_frames.clear()
                self._recent_bytes = 0
            else:
                # 日志监听线程可能稍后才收到异常；短暂保留这段时间的帧供补归档。
                self._recent_frames.append(frame)
                self._recent_bytes += len(data)
                while self._recent_frames and (
                    captured_ns - self._recent_frames[0].captured_ns > _ERROR_WINDOW_NS
                    or len(self._recent_frames) > self.max_recent_count
                    or self._recent_bytes > self.max_recent_bytes
                ):
                    self._recent_bytes -= len(self._recent_frames.popleft().data)
            # 关闭普通保存时，异常窗口内的新画面仍需单独写入归档。
            persist = save_history or self._in_error_window(captured_ns)
            if persist and self._make_room(frame):
                self._pending_count += 1
                self._pending_bytes += len(data)
                self._queue.append(frame)
                self._ready.notify()
        self._report_dropped()
        return filename

    def _record_drop(self, frame: Screenshot):
        self._dropped += 1
        self._dropped_bytes += len(frame.data)
        self._dropped_important += int(frame.important)

    def _make_room(self, frame: Screenshot) -> bool:
        # 调用时持有 _lock，容量同时计入等待中和正在写入的截图。
        count = self._pending_count + 1
        size = self._pending_bytes + len(frame.data)

        def fits():
            return count <= self.max_pending_count and size <= self.max_pending_bytes

        if fits():
            return True
        evicted = []
        if len(frame.data) <= self.max_pending_bytes:
            for waiting in self._queue:
                if waiting.important or any(
                    start <= waiting.captured_ns <= end
                    for start, end, _ in self._error_windows
                ):
                    continue
                evicted.append(waiting)
                count -= 1
                size -= len(waiting.data)
                if fits():
                    break
        if not fits():
            # 已在写入的图、关键截图不能淘汰；保持原队列，跳过新图。
            self._record_drop(frame)
            return False
        for waiting in evicted:
            self._queue.remove(waiting)
            self._pending_count -= 1
            self._pending_bytes -= len(waiting.data)
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
        """调用时持有 _lock；关闭普通保存时只排队报错后的画面。"""
        return any(
            int(archive_id) <= captured_ns <= end
            for _, end, archive_id in self._error_windows
        )

    def mark_error(self, timestamp_ns: int, message: str) -> str:
        """同一截图窗口内的错误合并归档，并延长至末次报错后五分钟。"""
        with self._ready:
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
                self._error_windows.append(
                    (scan_start, timestamp_ns + _ERROR_WINDOW_NS, archive_id)
                )
            else:
                start, old_end, archive_id = existing
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
                (scan_start, timestamp_ns, archive_id, message, 1, buffered)
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

    def _archive_frame(self, frame: Screenshot):
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
                        if archive_id in self._deleted_archives:
                            continue
                        if destination.exists():
                            archived = True
                            continue
                        if not self._ensure_archive_capacity_locked(
                            len(frame.data), archive_id
                        ):
                            self._archive_limit_warning()
                            continue
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        temporary = destination.with_suffix(".jpg.tmp")
                        try:
                            temporary.write_bytes(frame.data)
                            os.replace(temporary, destination)
                            if self._archive_bytes is not None:
                                self._archive_bytes += len(frame.data)
                            archived = True
                        finally:
                            temporary.unlink(missing_ok=True)
                except OSError as exc:
                    self._report_error("归档报错截图失败", exc)
        return archived

    def _copy_to_archive(self, source: Path, destination: Path):
        with self._archive_lock:
            if destination.parent.name in self._deleted_archives:
                return
            if destination.exists():
                return
            size = source.stat().st_size
            if not self._ensure_archive_capacity_locked(size, destination.parent.name):
                self._archive_limit_warning()
                return
            temporary = destination.with_suffix(".jpg.tmp")
            try:
                shutil.copy2(source, temporary)
                os.replace(temporary, destination)
                if self._archive_bytes is not None:
                    self._archive_bytes += size
            finally:
                temporary.unlink(missing_ok=True)

    def _archiver(self):
        while True:
            with self._ready:
                while not self._archive_queue and not self._stop.is_set():
                    if self._log_archive_queue:
                        deadline, archive_id = self._log_archive_queue[0]
                        remaining = (deadline - time.time_ns()) / 10**9
                        if remaining <= 0:
                            heapq.heappop(self._log_archive_queue)
                            break
                        self._ready.wait(timeout=remaining)
                    else:
                        self._ready.wait()
                else:
                    if not self._archive_queue:
                        return
                    start, end, archive_id, message, increment, buffered = (
                        self._archive_queue.popleft()
                    )
                    deadline = None
            if deadline is not None:
                self._save_error_logs(archive_id)
                continue
            destination = self.folder / "errors" / archive_id
            try:
                with self._archive_lock:
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
                        # 窗口延长后先撤销旧快照，再为更新后的记录检查可用空间。
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
                        temporary.write_bytes(contents)
                        os.replace(temporary, manifest)
                        if self._archive_bytes is not None:
                            self._archive_bytes += len(contents) - previous_size
                    finally:
                        temporary.unlink(missing_ok=True)
                while buffered:
                    self._archive_frame(buffered.popleft())
                # 先扫描已落盘图片；尚在队列里的图片随后由写盘线程归档。
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
                    if not folder.is_dir() or folder.name == "errors":
                        continue
                    if (
                        _HOUR_FOLDER.fullmatch(folder.name)
                        and folder.name not in hour_folders
                    ):
                        continue
                    for timestamp, name in self._images(folder):
                        if start <= timestamp <= scan_end:
                            try:
                                self._copy_to_archive(folder / name, destination / name)
                            except FileNotFoundError:
                                continue  # 清理线程可能刚删除到期原图。
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
            return {
                # 包含正在写入的一帧，因此慢磁盘下也能观察真实待写占用。
                "pending_count": self._pending_count,
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
            with self._ready:
                self._ready.wait_for(lambda: self._queue or self._stop.is_set())
                if not self._queue:
                    return
                frame = self._queue.popleft()
            try:
                started = time.monotonic()
                write_enabled = False
                history_enabled = False
                try:
                    history_enabled = self.retention_hours() > 0
                    write_enabled = history_enabled
                    if history_enabled:
                        self._write(frame)
                        self._archive_frame(frame)
                    else:
                        # 普通截图不落盘；报错窗口中的帧直接写入归档。
                        if not self._archive_frame(frame):
                            continue
                        write_enabled = True
                except Exception as exc:
                    with self._lock:
                        self._failed += 1
                    self._report_error(f"截图写入失败 {frame.filename}", exc)
                else:
                    with self._lock:
                        self._saved += 1
                        if frame.preview and history_enabled:
                            self._last_saved = frame.filename
                finally:
                    with self._lock:
                        self._pending_count -= 1
                        self._pending_bytes -= len(frame.data)
                        if write_enabled:
                            self._write_ms = (time.monotonic() - started) * 1000
                            self._queue_wait_ms = (started - frame.queued_at) * 1000
            finally:
                # 不让等待新任务的线程留住上一帧。
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

    def _remove_expired_error_archives(self, cutoff_ns):
        root = self.folder / "errors"
        if not root.exists():
            return
        with os.scandir(root) as entries:
            for entry in entries:
                if self._stop.is_set():
                    return
                if (
                    not entry.is_dir(follow_symlinks=False)
                    or not entry.name.isascii()
                    or not entry.name.isdigit()
                    or int(entry.name) >= cutoff_ns
                ):
                    continue
                try:
                    event = json.loads(
                        (Path(entry.path) / "event.json").read_text(encoding="utf-8")
                    )
                    if int(event.get("last_error_ns", entry.name)) >= cutoff_ns:
                        continue
                    self.delete_error_archive(entry.name)
                except (OSError, ValueError, TypeError, AttributeError) as exc:
                    self._cleanup_error(exc)

    def _trim_archive_limit(self):
        with self._archive_lock:
            limit = self.archive_limit_mb() * 1024**2
            if limit == 0:
                return
            # 定期重新扫描，兼容程序外部增删归档文件以及运行中修改上限。
            candidates = self._archive_candidates_locked()
            self._archive_bytes = sum(
                self._archive_size(self.folder / "errors" / archive_id)
                for _, _, archive_id in candidates
            )
            for _, _, archive_id in candidates:
                if self._archive_bytes <= limit or self._stop.is_set():
                    break
                self._delete_error_archive_locked(archive_id, require_manifest=False)

    def cleanup(self):
        # 防止手动清理和定时清理重叠，不占用预览/提交的锁。
        with self._cleanup_lock:
            started = time.monotonic()
            try:
                retention = max(0, self.retention_hours())
                # 保存开启时至少留五分钟，供迟到的错误日志归档前置截图。
                if retention:
                    retention = max(retention, 5 / 60)
                now_ns = time.time_ns()
                cutoff_ns = now_ns - int(retention * 3600 * 10**9)
                # 旧根目录仅做过期删除，不迁移也不建立路径映射。
                self._remove_expired(self.folder, cutoff_ns)
                if not self.folder.exists():
                    return
                self._remove_expired_error_archives(now_ns - _LOG_RETENTION_NS)
                self._trim_archive_limit()
                with os.scandir(self.folder) as entries:
                    for entry in entries:
                        if self._stop.is_set():
                            return
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                        if entry.name == "errors":
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

    def _report_status(self):
        stats = self.stats()
        state = tuple(stats[field] for field in _STATUS_FIELDS)
        # 清理耗时自然波动不代表截图活动，空闲时不重复打印全零统计。
        if stats["pending_count"] or state != self._last_reported_state:
            self.logger.debug("截图存储状态 %s", stats)
        self._last_reported_state = state

    def _cleaner(self):
        last_cleanup = float("-inf")
        last_archive_limit = None
        poll_interval = min(30, self.cleanup_interval)
        while not self._stop.is_set():
            archive_limit = self.archive_limit_mb()
            if (
                time.monotonic() - last_cleanup >= self.cleanup_interval
                or archive_limit != last_archive_limit
            ):
                self.cleanup()
                last_cleanup = time.monotonic()
                last_archive_limit = archive_limit
            self._report_status()
            if self._stop.wait(poll_interval):
                return
