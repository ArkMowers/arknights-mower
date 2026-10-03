"""截图清理游标：每批最多处理固定数量的目录条目或删除操作。"""

import errno
import heapq
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

HOUR_FOLDER = re.compile(r"\d{8}-\d{2}\Z")
IMPORTANT_FOLDERS = {"run_order", "workshop", "furniture", "solve_captcha"}


def screenshot_timestamp(name):
    stem, suffix = os.path.splitext(name)
    if suffix != ".jpg" or not stem.isascii() or not stem.isdigit():
        return None
    if len(stem) == 14:
        try:
            return int(datetime.strptime(stem, "%Y%m%d%H%M%S").timestamp() * 10**9)
        except ValueError:
            return None
    return int(stem)


def _entries(folder):
    """异常也是一个有界步骤；消失的目录视为空目录。"""
    try:
        # 根条目与子目录扫描可能跨批次；再次检查期间被替换的链接。
        if folder.is_symlink():
            return
        with os.scandir(folder) as entries:
            yield from entries
    except FileNotFoundError:
        return
    except OSError as exc:
        yield exc


def _delete(entry, cutoff):
    try:
        # scandir 句柄尚在时原路径也可能被替换；不能按旧 entry 删除链接目标。
        if Path(entry.path).parent.is_symlink():
            return 1, 0, None
        if entry.is_file(follow_symlinks=False):
            timestamp = screenshot_timestamp(entry.name)
            if timestamp is not None and timestamp < cutoff:
                Path(entry.path).unlink()
                return 1, 1, None
    except FileNotFoundError:
        pass
    except OSError as exc:
        return 1, 0, exc
    return 1, 0, None


class ScreenshotCleanup:
    """保留扫描位置直到本轮结束；调用方决定两批及两轮之间的间隔。

    ``step`` 的 scanned 计入所有目录条目，deleted 计入成功删除的文件和目录。
    两者分别不超过 batch_size；errors 返回本批的 I/O 异常而不中止后续扫描。
    一轮完成后的下一次 step 开始新一轮。close 释放所有目录句柄且不再开始扫描。
    """

    def __init__(
        self,
        folder: Path,
        retention_hours: Callable[[], float],
        *,
        time_ns: Callable[[], int] = time.time_ns,
        batch_size: int = 100,
    ):
        if batch_size <= 0:
            raise ValueError("截图清理批次大小必须大于 0")
        self.folder = Path(folder)
        self.retention_hours = retention_hours
        self.time_ns = time_ns
        self.batch_size = batch_size
        self._iterator = None
        self._closed = False

    def step(self) -> dict:
        result = {"scanned": 0, "deleted": 0, "complete": self._closed, "errors": ()}
        if self._closed:
            return result
        if self._iterator is None:
            self._iterator = self._run()
        errors = []
        for _ in range(self.batch_size):
            try:
                scanned, deleted, error = next(self._iterator)
            except StopIteration:
                self._iterator = None
                result["complete"] = True
                break
            except Exception as exc:
                # 动态配置和时钟也可能失败；释放本轮游标，允许下轮重试。
                self._iterator.close()
                self._iterator = None
                errors.append(exc)
                result["complete"] = True
                break
            result["scanned"] += scanned
            result["deleted"] += deleted
            if error is not None:
                errors.append(error)
        result["errors"] = tuple(errors)
        return result

    def close(self):
        self._closed = True
        if self._iterator is not None:
            self._iterator.close()
            self._iterator = None

    def _run(self):
        retention = max(0, self.retention_hours())
        if retention:
            retention = max(retention, 5 / 60)
        cutoff = self.time_ns() - int(retention * 3600 * 10**9)
        with_entries = _entries(self.folder)
        try:
            for entry in with_entries:
                if isinstance(entry, OSError):
                    yield 0, 0, entry
                    continue
                try:
                    directory = entry.is_dir(follow_symlinks=False)
                except FileNotFoundError:
                    yield 1, 0, None
                    continue
                except OSError as exc:
                    yield 1, 0, exc
                    continue
                if not directory:
                    yield _delete(entry, cutoff)
                    continue
                yield 1, 0, None
                if entry.name == "errors":
                    continue
                hour_folder = bool(HOUR_FOLDER.fullmatch(entry.name))
                if hour_folder:
                    try:
                        hour = datetime.strptime(entry.name, "%Y%m%d-%H")
                        if int(hour.timestamp() * 10**9) >= cutoff:
                            continue
                    except (OSError, ValueError) as exc:
                        yield 0, 0, exc
                        continue
                yield from self._clean_folder(
                    Path(entry.path), cutoff, entry.name in IMPORTANT_FOLDERS
                )
                if hour_folder:
                    try:
                        Path(entry.path).rmdir()
                    except FileNotFoundError:
                        pass
                    except OSError as exc:
                        # 写入中的临时文件或刚入队截图会让目录仍然非空。
                        if exc.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                            yield 0, 0, exc
                    else:
                        yield 0, 1, None
        finally:
            with_entries.close()

    def _clean_folder(self, folder, cutoff, important):
        if important:
            newest = []
            entries = _entries(folder)
            try:
                for entry in entries:
                    if isinstance(entry, OSError):
                        yield 0, 0, entry
                        # 首遍不完整时不能安全确定保留边界。
                        return
                    try:
                        if entry.is_file(follow_symlinks=False):
                            timestamp = screenshot_timestamp(entry.name)
                            if timestamp is not None:
                                if len(newest) < 100:
                                    heapq.heappush(newest, timestamp)
                                elif timestamp > newest[0]:
                                    heapq.heapreplace(newest, timestamp)
                    except FileNotFoundError:
                        pass
                    except OSError as exc:
                        yield 1, 0, exc
                        return
                    yield 1, 0, None
            finally:
                entries.close()
            if len(newest) < 100:
                return
            cutoff = newest[0]
        entries = _entries(folder)
        try:
            for entry in entries:
                if isinstance(entry, OSError):
                    yield 0, 0, entry
                else:
                    yield _delete(entry, cutoff)
        finally:
            entries.close()
