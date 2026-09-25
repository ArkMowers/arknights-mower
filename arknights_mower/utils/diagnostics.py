"""按时间关联运行日志和截图，供问题回看使用。"""

import bisect
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import SpooledTemporaryFile
from zipfile import ZIP_STORED, ZipFile

from arknights_mower.utils.screenshot import ScreenshotStore

_LOG_START = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
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


def timeline(log_folder: Path, screenshot_folder: Path, center: datetime, limit=1000):
    """返回指定时间前后五分钟的日志及最近截图。"""
    start, end = center - _WINDOW, center + _WINDOW
    images = screenshots_between(screenshot_folder, start, end)
    timestamps = [item[0] for item in images]
    rows = []
    if not log_folder.exists():
        return rows
    suffixes = {
        (start + timedelta(hours=offset)).strftime("%Y-%m-%d_%H") for offset in range(2)
    }
    files = [
        path
        for path in log_folder.iterdir()
        if path.is_file()
        and (
            path.name == "runtime.log"
            or path.name.removeprefix("runtime.log.") in suffixes
        )
    ]
    for path in sorted(files, key=lambda item: (item.name == "runtime.log", item.name)):
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if not _LOG_START.match(line):
                    if rows and len(rows[-1]["message"]) < 8000:
                        rows[-1]["message"] += line
                    continue
                try:
                    when = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                if not start <= when <= end:
                    continue
                # 文件日志精度为秒；包含同一秒中较早采集的画面。
                at_ns = int(when.timestamp() * 10**9) + 10**9 - 1
                index = bisect.bisect_right(timestamps, at_ns) - 1
                screenshot = None
                if index >= 0 and at_ns - timestamps[index] <= 30 * 10**9:
                    screenshot = images[index][1]
                rows.append(
                    {
                        "time": line[:19],
                        "message": line.rstrip(),
                        "screenshot": screenshot,
                    }
                )
    return rows[-limit:] if limit is not None else rows


def export_bundle(
    log_folder: Path, screenshot_folder: Path, center: datetime, archive_id=None
):
    """打包时间窗口内的完整日志和仍可读取的截图。调用方负责关闭返回的文件。"""
    start, end = center - _WINDOW, center + _WINDOW
    start_ns = int(start.timestamp() * 10**9)
    end_ns = int(end.timestamp() * 10**9)
    images = {}
    for timestamp, relative in screenshots_between(screenshot_folder, start, end):
        images[timestamp] = (screenshot_folder / relative, relative)

    # 报错归档中的画面即使已从普通截图目录清理，也应进入下载包。
    archive_root = screenshot_folder / "errors"
    if archive_id is not None:
        archives = [archive_root / archive_id]
    elif archive_root.exists():
        archives = [
            path
            for path in archive_root.iterdir()
            if path.is_dir()
            and path.name.isascii()
            and path.name.isdigit()
            and abs(int(path.name) - int(center.timestamp() * 10**9))
            <= 2 * int(_WINDOW.total_seconds() * 10**9)
        ]
    else:
        archives = []
    for folder in archives:
        if not folder.is_dir():
            continue
        for image in folder.glob("*.jpg"):
            timestamp = ScreenshotStore._timestamp(image.name)
            if timestamp is not None and start_ns <= timestamp <= end_ns:
                relative = image.relative_to(screenshot_folder).as_posix()
                if archive_id is not None or timestamp not in images:
                    images[timestamp] = (image, relative)

    saved = archive_root / archive_id / "logs.json" if archive_id else None
    if saved is not None and saved.is_file():
        rows = json.loads(saved.read_text(encoding="utf-8"))
    else:
        rows = timeline(log_folder, screenshot_folder, center, limit=None)

    output = SpooledTemporaryFile(max_size=16 * 1024**2, mode="w+b")
    try:
        with ZipFile(output, "w", compression=ZIP_STORED) as bundle:
            bundle.writestr(
                "说明.txt",
                f"日志调度导出\n时间范围：{start:%Y-%m-%d %H:%M:%S} 至 "
                f"{end:%Y-%m-%d %H:%M:%S}\n"
                f"日志：{len(rows)} 条\n截图：{len(images)} 张\n"
                "截图按采集时间排序；已过期或尚未写入的文件无法导出。\n",
            )
            bundle.writestr(
                "日志.txt",
                "\n".join(row["message"] for row in rows) + ("\n" if rows else ""),
            )
            bundle.writestr("日志.json", json.dumps(rows, ensure_ascii=False, indent=2))
            for _, (image, relative) in sorted(images.items()):
                try:
                    bundle.write(image, f"截图/{relative}")
                except FileNotFoundError:
                    # 清理线程可能在打包期间删除普通截图。
                    continue
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
            for image in sorted(folder.glob("*.jpg"))
        ]
        events.append(event)
    return sorted(events, key=lambda item: item["time_ns"], reverse=True)
