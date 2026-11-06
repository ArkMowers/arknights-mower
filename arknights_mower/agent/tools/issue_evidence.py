"""从日志调度的历史记录中挑选反馈所需的少量画面。"""

import hashlib
import json
import re
from bisect import bisect_right
from datetime import datetime
from zipfile import ZIP_DEFLATED, ZipFile

from arknights_mower.utils.diagnostics import _log_files, screenshots_between, timeline
from arknights_mower.utils.screenshot_cleanup import screenshot_timestamp

MAX_SCREENSHOTS = 4
MAX_IMAGE_BYTES = 512 * 1024
MAX_SCREENSHOT_BYTES = 2 * 1024**2
MAX_MAIL_BYTES = 8 * 1024**2
MAX_LOG_ROWS = 1000
MAX_EXCERPT_BYTES = 256 * 1024
MAX_LOG_ARCHIVE_BYTES = 3 * 1024**2
MAX_LOG_UNCOMPRESSED_BYTES = 64 * 1024**2
_LOG_START = re.compile(rb"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


def _write_log_archive(log_folder, start, end, output, archived):
    """按原始顺序流式保存区间日志，单次读取与附件总量均有上限。"""
    path = output / "runtime.zip"
    metadata = {
        "file": None,
        "record_count": 0,
        "bytes": 0,
        "uncompressed_bytes": 0,
        "first_time": None,
        "last_time": None,
        "truncated": False,
        "scan_complete": True,
        "source": "runtime_files",
        "archive_source_limited": False,
        "unreadable_files": [],
        "limits": {
            "compressed_bytes": MAX_LOG_ARCHIVE_BYTES,
            "uncompressed_bytes": MAX_LOG_UNCOMPRESSED_BYTES,
        },
        "stop_reason": None,
    }
    # 为最后一个压缩块和 ZIP 目录保留空间；每次最多写入 64 KiB。
    threshold = MAX_LOG_ARCHIVE_BYTES - 128 * 1024
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as bundle:
        with bundle.open("runtime.txt", "w") as destination:

            def write(data, when=None):
                if (
                    metadata["uncompressed_bytes"] + len(data)
                    > MAX_LOG_UNCOMPRESSED_BYTES
                    or bundle.fp.tell() >= threshold
                ):
                    metadata["truncated"] = True
                    metadata["scan_complete"] = False
                    metadata["stop_reason"] = (
                        "uncompressed_byte_limit"
                        if metadata["uncompressed_bytes"] + len(data)
                        > MAX_LOG_UNCOMPRESSED_BYTES
                        else "compressed_byte_limit"
                    )
                    return False
                destination.write(data)
                metadata["uncompressed_bytes"] += len(data)
                if when is not None:
                    stamp = str(when)
                    metadata["record_count"] += 1
                    metadata["first_time"] = min(metadata["first_time"] or stamp, stamp)
                    metadata["last_time"] = max(metadata["last_time"] or stamp, stamp)
                return True

            for source in _log_files(log_folder, start, end):
                if not metadata["scan_complete"]:
                    break
                try:
                    with source.open("rb") as stream:
                        selected = False
                        line_start = True
                        while chunk := stream.readline(64 * 1024):
                            when = None
                            if line_start and _LOG_START.match(chunk):
                                try:
                                    when = datetime.strptime(
                                        chunk[:19].decode("ascii"), "%Y-%m-%d %H:%M:%S"
                                    )
                                except ValueError:
                                    selected = False
                                else:
                                    selected = start <= when <= end
                            if selected and not write(chunk, when):
                                break
                            line_start = chunk.endswith(b"\n")
                except OSError:
                    metadata["unreadable_files"].append(source.name)
            # 归档保留片段可能与普通日志重复，不能把它当作完整历史。
            if archived and metadata["scan_complete"]:
                has_runtime = bool(metadata["record_count"])
                for row in archived:
                    data = (row["message"] + "\n").encode("utf-8")
                    if not write(data, datetime.fromisoformat(row["time"])):
                        break
                    metadata["archive_source_limited"] = True
                    metadata["source"] = (
                        "runtime_files_and_error_archive_excerpt"
                        if has_runtime
                        else "error_archive_excerpt"
                    )
    metadata["scan_complete"] &= not bool(metadata["unreadable_files"])
    metadata["bytes"] = path.stat().st_size
    if not metadata["record_count"] or metadata["bytes"] > MAX_LOG_ARCHIVE_BYTES:
        metadata["truncated"] |= metadata["bytes"] > MAX_LOG_ARCHIVE_BYTES
        metadata["scan_complete"] = False
        path.unlink()
        return None, metadata
    metadata["file"] = path.name
    return path, metadata


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
            for image in archive.iterdir():
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
    log_archive, archive_info = _write_log_archive(
        log_folder, start, end, output, archived
    )
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
            candidates.append(
                (images[index][1], reason, signature, when, stamps[index])
            )

    attachments, selected, digests, seen_paths = [], [], set(), set()
    selected_errors = set()
    total = 0
    for relative, reason, signature, anchor_time, capture_ns in candidates:
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
            {
                "file": destination.name,
                "source": relative,
                "reason": reason,
                "anchor_time": str(anchor_time),
                "captured_at": datetime.fromtimestamp(capture_ns / 10**9)
                .astimezone()
                .isoformat(),
                "offset_seconds": capture_ns / 10**9 - anchor_time.timestamp(),
            }
        )

    log_path = output / "runtime.txt"
    # 纯文本只供快速浏览；压缩附件按所选区间独立收集。
    excerpt, excerpt_bytes = [], 0
    for row in reversed(rows):
        text = row["message"][:1000]
        size = len((text + "\n").encode("utf-8"))
        if excerpt_bytes + size > MAX_EXCERPT_BYTES:
            truncated = True
            break
        excerpt.append({**row, "text": text})
        excerpt_bytes += size
    excerpt.reverse()
    truncated |= archive_info["record_count"] > len(excerpt)
    log_path.write_text("\n".join(row["text"] for row in excerpt), encoding="utf-8")
    manifest = output / "evidence.json"
    manifest.write_text(
        json.dumps(
            {
                "start": str(start),
                "end": str(end),
                "screenshots": selected,
                "log_archive": archive_info,
                "excerpt": {
                    "first_time": min((row["time"] for row in excerpt), default=None),
                    "last_time": max((row["time"] for row in excerpt), default=None),
                    "record_count": len(excerpt),
                },
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
    return [log_path, manifest, *([log_archive] if log_archive else []), *attachments]
