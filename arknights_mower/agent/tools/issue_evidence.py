"""从日志调度的历史记录中挑选反馈所需的少量画面。"""

import hashlib
import json
import re
from bisect import bisect_right
from datetime import datetime

from arknights_mower.utils.diagnostics import screenshots_between, timeline
from arknights_mower.utils.screenshot_cleanup import screenshot_timestamp

MAX_SCREENSHOTS = 4
MAX_IMAGE_BYTES = 512 * 1024
MAX_SCREENSHOT_BYTES = 2 * 1024**2
MAX_MAIL_BYTES = 8 * 1024**2
MAX_LOG_ROWS = 1000


def parse_interval(start_time, end_time):
    start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
    if not 0 < (end - start).total_seconds() <= 900:
        raise ValueError("结束时间须晚于开始时间，且问题时间范围不超过15分钟。")
    return start, end


def _images(folder, start, end):
    images = dict(screenshots_between(folder, start, end))
    archives = folder / "errors"
    if archives.is_dir():
        for archive in sorted(archives.iterdir()):
            if not archive.name.isascii() or not archive.name.isdigit():
                continue
            for image in archive.glob("*.jpg"):
                stamp = screenshot_timestamp(image.name)
                if (
                    stamp is not None
                    and start.timestamp() * 10**9 <= stamp <= end.timestamp() * 10**9
                ):
                    images.setdefault(stamp, image.relative_to(folder).as_posix())
    return sorted(images.items())


def _archived_rows(folder, start, end):
    root = folder / "errors"
    if not root.is_dir():
        return []
    rows = []
    for archive in sorted(root.iterdir()):
        if not archive.name.isascii() or not archive.name.isdigit():
            continue
        try:
            with (archive / "logs.json").open("rb") as stream:
                data = stream.read(8 * 1024**2 + 1)
            if len(data) > 8 * 1024**2:
                continue
            saved = json.loads(data)
            if not isinstance(saved, list):
                continue
            for row in saved:
                if not isinstance(row, dict) or not isinstance(row.get("message"), str):
                    continue
                try:
                    when = datetime.strptime(row.get("time", ""), "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    continue
                if start <= when <= end:
                    rows.append({"time": row["time"], "message": row["message"][:8000]})
                    rows = rows[-(MAX_LOG_ROWS + 1) :]
        except (OSError, ValueError):
            continue
    return rows


def collect_evidence(
    log_folder, screenshot_folder, start, end, output, screenshot_times=None
):
    """复用日志调度的时间关联，只附指定时刻或异常附近的画面。"""
    if screenshot_times is not None and (
        not isinstance(screenshot_times, list)
        or len(screenshot_times) > MAX_SCREENSHOTS
    ):
        raise ValueError("关键截图时间最多提供4个。")
    requested = []
    for value in screenshot_times or []:
        when = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        if not start <= when <= end:
            raise ValueError("关键截图时间须位于问题时间范围内。")
        requested.append((when, "AI 根据问题分析指定的关键时刻"))

    try:
        images = _images(screenshot_folder, start, end)
    except OSError:
        images = []
    rows = timeline(
        log_folder,
        screenshot_folder,
        start,
        limit=MAX_LOG_ROWS + 1,
        start=start,
        end=end,
        images=images,
    )
    # 异常归档可在普通日志及截图过期后继续提供证据。
    archived = _archived_rows(screenshot_folder, start, end)
    rows = sorted(
        {(row["time"], row["message"]): row for row in archived + rows}.values(),
        key=lambda row: row["time"],
    )
    truncated = len(rows) > MAX_LOG_ROWS
    rows = rows[-MAX_LOG_ROWS:]
    if not rows:
        raise ValueError("未找到对应时间的日志记录，无法上报。")
    # 优先保留不同错误首次可读取的画面，再考虑警告。
    errors, warnings = [], []
    for row in rows:
        match = re.match(
            r"^.{19}(?:,\d+)? \S+ (CRITICAL|ERROR|WARNING)(?: (.*))?$",
            row["message"],
            re.S,
        )
        if match is None:
            continue
        signature = (match[1], re.sub(r"\d+", "N", (match[2] or "").partition("\n")[0]))
        target = warnings if match[1] == "WARNING" else errors
        target.append(
            (datetime.fromisoformat(row["time"]), row["message"][:500], signature)
        )
    anchors = (
        [(when, reason, str(when)) for when, reason in requested]
        if screenshot_times is not None
        else errors + warnings
    )
    stamps = [stamp for stamp, _ in images]
    candidates = []
    for when, reason, signature in anchors:
        # 秒级日志覆盖同秒截图，只使用报错前30秒内最后一帧。
        at = int(when.timestamp() * 10**9) + 10**9 - 1
        index = bisect_right(stamps, at) - 1
        if index >= 0 and at - stamps[index] <= 30 * 10**9:
            candidates.append((images[index][1], reason, signature))

    attachments, selected, digests, seen_paths = [], [], set(), set()
    selected_errors = set()
    total = 0
    for relative, reason, signature in candidates:
        if len(selected) >= MAX_SCREENSHOTS:
            break
        if relative in seen_paths or signature in selected_errors:
            continue
        seen_paths.add(relative)
        path = screenshot_folder / relative
        try:
            if not path.resolve().is_relative_to(screenshot_folder.resolve()):
                continue
            with path.open("rb") as stream:
                data = stream.read(MAX_IMAGE_BYTES + 1)
        except OSError:
            continue
        digest = hashlib.sha256(data).digest()
        if (
            len(data) > MAX_IMAGE_BYTES
            or total + len(data) > MAX_SCREENSHOT_BYTES
            or digest in digests
        ):
            continue
        digests.add(digest)
        selected_errors.add(signature)
        total += len(data)
        destination = output / f"screenshot-{len(selected) + 1}-{path.name}"
        destination.write_bytes(data)
        attachments.append(destination)
        selected.append(
            {"file": destination.name, "source": relative, "reason": reason}
        )

    log_path = output / "runtime.txt"
    # 最多1000条，每条最多1000字符，避免文字日志占满邮件。
    log_path.write_text(
        "\n".join(row["message"][:1000] for row in rows), encoding="utf-8"
    )
    manifest = output / "evidence.json"
    manifest.write_text(
        json.dumps(
            {
                "start": str(start),
                "end": str(end),
                "screenshots": selected,
                "log_rows_truncated": truncated,
                "log_messages_truncated": any(
                    len(row["message"]) > 1000 for row in rows
                ),
                "selection": "截图按关键时刻或异常日志关联筛选，未分析画面内容；重复、超限或已清理画面不附加。",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return [log_path, manifest, *attachments]
