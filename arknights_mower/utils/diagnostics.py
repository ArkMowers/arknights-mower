"""按时间关联运行日志和截图，供问题回看使用。"""

import bisect
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

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


def timeline(log_folder: Path, screenshot_folder: Path, center: datetime):
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
    return rows[-1000:]


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
