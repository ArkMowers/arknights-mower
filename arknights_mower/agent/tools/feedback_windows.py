"""分段收集反馈所需的较早记录与后续处理记录。"""

import json
import re
from datetime import datetime
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from arknights_mower.agent.tools.feedback_records import (
    MAX_FILE_BYTES,
    MAX_ROWS,
    QUERY_TIMEOUT_SECONDS,
    collect_feedback_records,
)
from arknights_mower.agent.tools.issue_evidence import (
    MAX_LOG_ARCHIVE_BYTES,
    MAX_LOG_UNCOMPRESSED_BYTES,
    collect_evidence,
    parse_interval,
)

MAX_FEEDBACK_WINDOWS = 3
MAX_REASON_LENGTH = 500
_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}")
_READ_BYTES = 64 * 1024


def _primary_time(value):
    if isinstance(value, str) and _TIMESTAMP.fullmatch(value):
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    if isinstance(value, datetime) and value.tzinfo is None and value.microsecond == 0:
        return value
    raise ValueError("问题时间须使用本地 YYYY-MM-DD HH:MM:SS。")


def validate_feedback_windows(windows, primary_start, primary_end):
    """先校验所有附加时段，包含结束秒的时段不得相互重叠。"""
    if windows is None:
        return []
    if not isinstance(windows, list) or len(windows) > MAX_FEEDBACK_WINDOWS:
        raise ValueError("附加证据时段须为列表，最多提供3段。")
    if not windows:
        return []
    primary_start, primary_end = (
        _primary_time(primary_start),
        _primary_time(primary_end),
    )
    parse_interval(str(primary_start), str(primary_end))
    intervals = [(primary_start, primary_end)]
    selected = []
    for window in windows:
        if not isinstance(window, dict) or set(window) != {
            "start_time",
            "end_time",
            "reason",
        }:
            raise ValueError("每段附加证据须提供开始时间、结束时间和补充原因。")
        start_text, end_text, reason = (
            window["start_time"],
            window["end_time"],
            window["reason"],
        )
        if any(
            not isinstance(value, str) or not _TIMESTAMP.fullmatch(value)
            for value in (start_text, end_text)
        ):
            raise ValueError("附加证据时间须使用本地 YYYY-MM-DD HH:MM:SS。")
        if (
            not isinstance(reason, str)
            or not reason.strip()
            or len(reason) > MAX_REASON_LENGTH
        ):
            raise ValueError("每段附加证据须填写不超过500字的补充原因。")
        start, end = parse_interval(start_text, end_text)
        if any(
            start <= previous_end and end >= previous_start
            for previous_start, previous_end in intervals
        ):
            raise ValueError(
                "附加证据时段不得与问题时段或其他附加时段重叠，包含结束秒。"
            )
        intervals.append((start, end))
        selected.append({"start": start, "end": end, "reason": reason.strip()})
    return selected


def _extract_log(source, destination):
    """将内部日志归档分块展开为最终附件成员，不在内存中展开全文。"""
    written = 0
    try:
        with ZipFile(source) as archive, archive.open("runtime.txt") as stream:
            with destination.open("wb") as output:
                while chunk := stream.read(_READ_BYTES):
                    written += len(chunk)
                    if written > MAX_LOG_UNCOMPRESSED_BYTES:
                        raise ValueError("附加时段日志超过未压缩容量限制。")
                    output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _collect_logs(log_folder, screenshot_folder, window, directory, prefix):
    evidence = {
        "start": str(window["start"]),
        "end": str(window["end"]),
        "screenshots": [],
    }
    members = {}
    logs = {"status": "unavailable", "reason": None}
    try:
        paths = collect_evidence(
            log_folder,
            screenshot_folder,
            window["start"],
            window["end"],
            directory,
            screenshot_times=[],
        )
        files = {path.name: path for path in paths}
        evidence = json.loads(files["evidence.json"].read_text(encoding="utf-8"))
        if "runtime.txt" in files:
            members[f"{prefix}/runtime.txt"] = files["runtime.txt"]
        archive = evidence.get("log_archive", {})
        if "runtime.zip" in files:
            destination = directory / "runtime.log"
            _extract_log(files["runtime.zip"], destination)
            members[f"{prefix}/runtime.log"] = destination
            archive.update(file=f"{prefix}/runtime.log", compression="outer_bundle")
            logs["status"] = (
                "partial"
                if archive.get("truncated")
                or not archive.get("scan_complete")
                or archive.get("archive_source_limited")
                else "exported"
            )
        else:
            logs.update(status="partial", reason="interval_log_unavailable")
        logs.update(log_archive=archive, excerpt=evidence.get("excerpt", {}))
    except (OSError, ValueError, BadZipFile, KeyError, RuntimeError) as exc:
        logs.update(
            status="partial" if members else "unavailable",
            reason=(
                "no_logs"
                if isinstance(exc, ValueError)
                and str(exc) == "未找到对应时间的日志记录，无法上报。"
                else "collection_failed"
            ),
            error_type=type(exc).__name__,
        )
        archive = evidence.get("log_archive")
        if isinstance(archive, dict):
            archive["file"] = None
    evidence["logs"] = logs
    return members, evidence, logs


def collect_feedback_windows(
    windows,
    primary_start,
    primary_end,
    log_folder,
    screenshot_folder,
    db_path,
    output,
) -> tuple[dict[str, Path], dict]:
    """附加时段分别读取日志及数据库历史，失败结果写入对应清单。"""
    selected = validate_feedback_windows(windows, primary_start, primary_end)
    metadata = {
        "limits": {
            "max_windows": MAX_FEEDBACK_WINDOWS,
            "max_seconds_per_window": 900,
            "max_reason_characters": MAX_REASON_LENGTH,
            "compressed_log_bytes_per_window": MAX_LOG_ARCHIVE_BYTES,
            "uncompressed_log_bytes_per_window": MAX_LOG_UNCOMPRESSED_BYTES,
            "compressed_log_bytes_total": MAX_LOG_ARCHIVE_BYTES * MAX_FEEDBACK_WINDOWS,
            "uncompressed_log_bytes_total": MAX_LOG_UNCOMPRESSED_BYTES
            * MAX_FEEDBACK_WINDOWS,
            "database_rows_per_table_per_window": MAX_ROWS,
            "database_bytes_per_table_per_window": MAX_FILE_BYTES,
            "database_query_seconds_per_table_per_window": QUERY_TIMEOUT_SECONDS,
            "additional_screenshots": 0,
        },
        "selection_note": (
            "仅收集所列附加时段，包含结束秒；各段分别列出实际保留记录与省略原因。"
            "各段之间未收集的时间不由相邻记录补足，扫描完成或空结果均不证明连续完整覆盖。"
            "附加时段不增加截图，最终邮件仍受整体容量限制。"
        ),
        "windows": [],
    }
    members = {}
    for index, window in enumerate(selected, 1):
        prefix = f"windows/{index}"
        directory = Path(output) / "windows" / str(index)
        directory.mkdir(parents=True, exist_ok=True)
        window_members, evidence, logs = _collect_logs(
            Path(log_folder), Path(screenshot_folder), window, directory, prefix
        )
        paths, database = collect_feedback_records(
            Path(db_path), window["start"], window["end"], directory
        )
        for table in database["tables"].values():
            if table["file"] is not None:
                table["file"] = f"{prefix}/{table['file']}"
        for path in paths:
            window_members[f"{prefix}/{path.name}"] = path
        info = {
            "index": index,
            "start_time": str(window["start"]),
            "end_time": str(window["end"]),
            "reason": window["reason"],
            "members": [*window_members, f"{prefix}/evidence.json"],
            "logs": logs,
            "database_records": database,
        }
        evidence.update(
            additional_window={
                key: info[key] for key in ("index", "reason", "members")
            },
            database_records=database,
            selection_note=metadata["selection_note"],
        )
        manifest = directory / "evidence.json"
        manifest.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        window_members[f"{prefix}/evidence.json"] = manifest
        members.update(window_members)
        metadata["windows"].append(info)
    return members, metadata
