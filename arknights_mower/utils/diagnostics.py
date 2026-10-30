"""按时间关联运行日志和截图，供问题回看使用。"""

import bisect
import json
import re
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import SpooledTemporaryFile
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from arknights_mower.utils.screenshot import (
    ARCHIVE_METADATA_RESERVE,
    MAX_ARCHIVE_BYTES,
    ScreenshotStore,
)

_LOG_START = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
_LINE_END = re.compile(b"\r\n|\r|\n")
_WINDOW = timedelta(minutes=5)


def screenshots_between(folder: Path, start: datetime, end: datetime):
    start_ns = int(start.timestamp() * 10**9)
    end_ns = int(end.timestamp() * 10**9)
    images = []
    if not folder.exists():
        return images
    hour_names = set()
    hour = start.replace(minute=0, second=0, microsecond=0)
    while hour <= end:
        hour_names.add(hour.strftime("%Y%m%d-%H"))
        hour += timedelta(hours=1)
    for directory in (folder, *folder.iterdir()):
        if not directory.is_dir() or directory.name == "errors":
            continue
        if (
            re.fullmatch(r"\d{8}-\d{2}", directory.name)
            and directory.name not in hour_names
        ):
            continue
        for image in directory.iterdir():
            timestamp = ScreenshotStore._timestamp(image.name)
            if timestamp is not None and start_ns <= timestamp <= end_ns:
                images.append((timestamp, image.relative_to(folder).as_posix()))
    return sorted(images)


def archive_window(folder: Path, center: datetime):
    """返回报错合并后的完整窗口；旧归档沿用单次报错窗口。"""
    try:
        event = json.loads((folder / "event.json").read_text(encoding="utf-8"))
        first = int(event["time_ns"])
        last = max(first, int(event.get("last_error_ns", first)))
        return (
            datetime.fromtimestamp(first / 10**9) - _WINDOW,
            datetime.fromtimestamp(last / 10**9) + _WINDOW,
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return center - _WINDOW, center + _WINDOW


def _reverse_lines(stream, block_size=64 * 1024):
    """从文件末尾分块读取，完整拼接 UTF-8 行后再解码。"""
    position = stream.seek(0, 2)
    pending = b""
    last_line = True
    while position:
        size = min(position, block_size)
        position -= size
        stream.seek(position)
        chunk = stream.read(size)
        if position and chunk.startswith(b"\n"):
            stream.seek(position - 1)
            if stream.read(1) == b"\r":
                position -= 1
                chunk = b"\r" + chunk
        lines = _LINE_END.split(chunk + pending)
        pending = lines[0]
        for line in reversed(lines[1:]):
            if last_line:
                last_line = False
                if not line:
                    continue
            yield line.decode("utf-8", errors="replace")
    if pending:
        yield pending.decode("utf-8", errors="replace")


def _recent_records(files, start, end, limit):
    """按原文件及行顺序保留末尾记录，不假定日志时间严格递增。"""
    retained = []
    for path in reversed(files):
        details = deque()
        detail_size = 0
        with path.open("rb") as stream:
            for line in _reverse_lines(stream):
                if not _LOG_START.match(line):
                    details.appendleft(line)
                    detail_size += len(line) + 1
                    # 保留正文开头足够的续行，仍按原先的 8000 字符规则截断。
                    while detail_size - len(details[-1]) - 1 >= 8000:
                        detail_size -= len(details.pop()) + 1
                    continue
                try:
                    when = datetime.fromisoformat(line[:19])
                except ValueError:
                    when = None
                if when is not None and start <= when <= end:
                    message = line.rstrip()
                    for detail in details:
                        if len(message) >= 8000:
                            break
                        message += "\n" + detail
                    retained.append((when, message))
                    if len(retained) == limit:
                        return reversed(retained)
                details.clear()
                detail_size = 0
    return reversed(retained)


def _log_row(when, message, timestamps, images):
    # 文件日志精度为秒；包含同一秒中较早采集的画面。
    at_ns = int(when.timestamp() * 10**9) + 10**9 - 1
    index = bisect.bisect_right(timestamps, at_ns) - 1
    screenshot = None
    if index >= 0 and at_ns - timestamps[index] <= 30 * 10**9:
        screenshot = images[index][1]
    return {"time": message[:19], "message": message, "screenshot": screenshot}


def _log_files(log_folder, start, end):
    if not log_folder.exists():
        return []
    suffixes = set()
    hour = start.replace(minute=0, second=0, microsecond=0)
    while hour <= end:
        suffixes.add(hour.strftime("%Y-%m-%d_%H"))
        hour += timedelta(hours=1)
    files = [
        path
        for path in log_folder.iterdir()
        if path.is_file()
        and (
            path.name == "runtime.log"
            or path.name.removeprefix("runtime.log.") in suffixes
        )
    ]
    return sorted(files, key=lambda item: (item.name == "runtime.log", item.name))


def timeline(
    log_folder: Path,
    screenshot_folder: Path,
    center: datetime,
    limit=1000,
    *,
    start=None,
    end=None,
    images=None,
):
    """返回指定时间窗口的日志及最近截图。"""
    start = start or center - _WINDOW
    end = end or center + _WINDOW
    if images is None:
        images = screenshots_between(screenshot_folder, start, end)
    if limit is not None and limit > 0:
        timestamps = [item[0] for item in images]
        return [
            _log_row(when, message, timestamps, images)
            for when, message in _recent_records(
                _log_files(log_folder, start, end), start, end, limit
            )
        ]
    rows = list(_log_rows(log_folder, start, end, images))
    return rows[-limit:] if limit is not None else rows


def _log_rows(log_folder, start, end, images, *, detail_limit=8000):
    """逐条读取范围内的日志，避免导出长时段时积累全部正文。"""
    timestamps = [item[0] for item in images]
    for path in _log_files(log_folder, start, end):
        current_row = None
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if not _LOG_START.match(line):
                    if current_row is not None and (
                        detail_limit is None
                        or len(current_row["message"]) < detail_limit
                    ):
                        current_row["message"] += "\n" + line.rstrip("\r\n")
                    continue
                if current_row is not None:
                    yield current_row
                current_row = None
                try:
                    when = datetime.fromisoformat(line[:19])
                except ValueError:
                    continue
                if not start <= when <= end:
                    continue
                current_row = _log_row(when, line.rstrip(), timestamps, images)
        if current_row is not None:
            yield current_row


def export_bundle(
    log_folder: Path,
    screenshot_folder: Path,
    center: datetime,
    archive_id=None,
    *,
    start=None,
    end=None,
    include_screenshots=True,
    scheduling_plan=None,
):
    """打包时间窗口内的完整日志和仍可读取的截图。调用方负责关闭返回的文件。"""
    archive_root = screenshot_folder / "errors"
    start, end = (
        archive_window(archive_root / archive_id, center)
        if archive_id is not None
        else (start or center - _WINDOW, end or center + _WINDOW)
    )
    start_ns = int(start.timestamp() * 10**9)
    end_ns = int(end.timestamp() * 10**9)
    images = {}
    for timestamp, relative in (
        screenshots_between(screenshot_folder, start, end)
        if include_screenshots and archive_id is None
        else []
    ):
        images[timestamp] = (screenshot_folder / relative, relative)

    # 报错归档中的画面即使已从普通截图目录清理，也应进入下载包。
    if not include_screenshots:
        archives = []
    elif archive_id is not None:
        archives = [archive_root / archive_id]
    elif archive_root.exists():
        archives = [
            path
            for path in archive_root.iterdir()
            if path.is_dir() and path.name.isascii() and path.name.isdigit()
        ]
    else:
        archives = []
    for folder in archives:
        if not folder.is_dir():
            continue
        for image in folder.iterdir():
            timestamp = ScreenshotStore._timestamp(image.name)
            if timestamp is not None and start_ns <= timestamp <= end_ns:
                relative = image.relative_to(screenshot_folder).as_posix()
                if archive_id is not None or timestamp not in images:
                    images[timestamp] = (image, relative)

    plan_contents = (
        json.dumps(scheduling_plan, ensure_ascii=False, indent=2).encode("utf-8")
        if scheduling_plan is not None
        else None
    )
    truncated = False
    payload_bytes = len(plan_contents or b"")
    if archive_id is not None:
        selected = {}
        for timestamp, (image, relative) in sorted(images.items()):
            try:
                size = image.stat().st_size
            except FileNotFoundError:
                continue
            if payload_bytes + size > MAX_ARCHIVE_BYTES - ARCHIVE_METADATA_RESERVE:
                truncated = True
                continue
            selected[timestamp] = (image, relative)
            payload_bytes += size
        images = selected
        try:
            event = json.loads(
                (archive_root / archive_id / "event.json").read_text("utf-8")
            )
            truncated |= bool(event.get("truncated"))
        except (OSError, ValueError):
            pass

    saved = archive_root / archive_id / "logs.json" if archive_id else None
    if saved is not None and saved.is_file():
        rows = json.loads(saved.read_text(encoding="utf-8"))
    else:
        rows = _log_rows(log_folder, start, end, [], detail_limit=None)

    output = SpooledTemporaryFile(max_size=16 * 1024**2, mode="w+b")
    try:
        with ZipFile(output, "w", compression=ZIP_STORED) as bundle:
            count = 0
            log_info = ZipInfo("日志.txt")
            log_info.compress_type = (
                ZIP_STORED if archive_id is not None else ZIP_DEFLATED
            )
            with bundle.open(log_info, "w", force_zip64=True) as stream:
                log_bytes = 0
                for row in rows:
                    data = (row["message"] + "\n").encode("utf-8")
                    if archive_id is not None and (
                        payload_bytes + log_bytes + len(data)
                        > MAX_ARCHIVE_BYTES - ARCHIVE_METADATA_RESERVE
                    ):
                        truncated = True
                        break
                    stream.write(data)
                    log_bytes += len(data)
                    count += 1
            if plan_contents is not None:
                bundle.writestr("排班表.json", plan_contents)
            image_count = 0
            for _, (image, relative) in sorted(images.items()):
                try:
                    bundle.write(image, f"截图/{relative}")
                    image_count += 1
                except FileNotFoundError:
                    # 清理线程可能在打包期间删除普通截图。
                    continue
            bundle.writestr(
                "说明.txt",
                f"日志调度导出\n时间范围：{start:%Y-%m-%d %H:%M:%S} 至 "
                f"{end:%Y-%m-%d %H:%M:%S}\n"
                f"日志：{count} 条\n截图：{image_count} 张\n"
                f"包含截图：{'是' if include_screenshots else '否'}\n"
                "排班表为导出时当前保存的配置，不代表日志发生时的排班。\n"
                "截图按采集时间排序；已过期或尚未写入的文件无法导出。\n"
                + ("归档达到上限，部分截图或日志已省略。\n" if truncated else ""),
            )
        output.seek(0)
        return output
    except Exception:
        output.close()
        raise


def error_events(screenshot_folder: Path):
    root = screenshot_folder / "errors"
    if not root.exists():
        return []
    events = []
    for folder in root.iterdir():
        if not folder.is_dir() or not folder.name.isdigit():
            continue
        manifest = folder / "event.json"
        try:
            event = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        event["id"] = folder.name
        event["screenshots"] = [
            f"errors/{folder.name}/{image.name}"
            for image in sorted(folder.iterdir())
            if ScreenshotStore._timestamp(image.name) is not None
        ]
        events.append(event)
    return sorted(events, key=lambda item: item["time_ns"], reverse=True)
