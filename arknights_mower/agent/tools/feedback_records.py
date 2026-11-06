"""只读导出反馈时间范围内的任务和干员历史。"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from time import monotonic

MAX_ROWS = 5000
MAX_FILE_BYTES = 1024 * 1024
QUERY_TIMEOUT_SECONDS = 2.0

_TABLES = {
    "log": (
        "task_history.jsonl",
        ("time", "task", "level", "message"),
        "time",
        "Unix seconds",
    ),
    "agent_action": (
        "operator_history.jsonl",
        (
            "name",
            "agent_current_room",
            "current_room",
            "is_high",
            "agent_group",
            "mood",
            "current_time",
            "related_operator",
            "mood_event",
            "context_key",
            "current_index",
        ),
        "current_time",
        "local datetime text, original precision",
    ),
}


def _connect_readonly(path):
    connection = sqlite3.connect(
        Path(path).resolve().as_uri() + "?mode=ro",
        uri=True,
        timeout=QUERY_TIMEOUT_SECONDS,
    )
    try:
        connection.execute("PRAGMA query_only = ON")
    except Exception:
        connection.close()
        raise
    return connection


def _collect_table(db_path, table, spec, start, end, output):
    filename, columns, time_column, time_format = spec
    metadata = {
        "status": "unavailable",
        "file": None,
        "row_count": 0,
        "first_time": None,
        "last_time": None,
        "time_format": time_format,
        "truncated": False,
        "bytes": 0,
        "scan_complete": False,
        "missing_columns": [],
        "reason": None,
    }
    destination = None
    deadline = monotonic() + QUERY_TIMEOUT_SECONDS
    try:
        if not db_path.is_file():
            metadata["reason"] = "missing_database"
            return None, metadata
        # mode=ro 同时防止检查后文件消失时意外创建数据库。
        with closing(_connect_readonly(db_path)) as connection:
            connection.set_progress_handler(lambda: monotonic() >= deadline, 1000)
            remaining_ms = max(0, int((deadline - monotonic()) * 1000))
            connection.execute(f"PRAGMA busy_timeout = {remaining_ms}")
            available = {
                row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')
            }
            if not available:
                metadata["reason"] = "missing_table"
                return None, metadata
            metadata["missing_columns"] = [
                col for col in columns if col not in available
            ]
            if time_column not in available:
                metadata["reason"] = "missing_time_column"
                return None, metadata
            if monotonic() >= deadline:
                metadata["reason"] = "query_timeout"
                return None, metadata
            selected = [col for col in columns if col in available]
            fields = ", ".join(f'"{col}"' for col in selected)
            if table == "log":
                bounds = (start.timestamp(), end.timestamp() + 1)
            else:
                bounds = (
                    start.strftime("%Y-%m-%d %H:%M:%S"),
                    (end + timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S"),
                )
            remaining_ms = max(0, int((deadline - monotonic()) * 1000))
            connection.execute(f"PRAGMA busy_timeout = {remaining_ms}")
            cursor = connection.execute(
                f'SELECT {fields} FROM "{table}" '
                f'WHERE "{time_column}" >= ? AND "{time_column}" < ? '
                f'ORDER BY "{time_column}" ASC LIMIT ?',
                (*bounds, MAX_ROWS + 1),
            )
            output.mkdir(parents=True, exist_ok=True)
            candidate = output / filename
            with candidate.open("wb") as stream:
                destination = candidate
                metadata["file"] = filename
                for row in cursor:
                    if monotonic() >= deadline:
                        metadata.update(truncated=True, reason="query_timeout")
                        break
                    if metadata["row_count"] >= MAX_ROWS:
                        metadata.update(truncated=True, reason="row_limit")
                        break
                    record = dict(zip(selected, row))
                    data = (json.dumps(record, ensure_ascii=False) + "\n").encode(
                        "utf-8"
                    )
                    if metadata["bytes"] + len(data) > MAX_FILE_BYTES:
                        metadata.update(truncated=True, reason="byte_limit")
                        break
                    stream.write(data)
                    metadata["bytes"] += len(data)
                    metadata["row_count"] += 1
                    if metadata["first_time"] is None:
                        metadata["first_time"] = record[time_column]
                    metadata["last_time"] = record[time_column]
                else:
                    metadata["scan_complete"] = True
            if metadata["truncated"] or metadata["missing_columns"]:
                metadata["status"] = "partial"
            else:
                metadata["status"] = "exported" if metadata["row_count"] else "empty"
            if metadata["missing_columns"] and metadata["reason"] is None:
                metadata["reason"] = "missing_columns"
    except (sqlite3.Error, OSError, TypeError, ValueError) as exc:
        metadata["status"] = "partial" if destination is not None else "unavailable"
        metadata["truncated"] = destination is not None
        metadata["scan_complete"] = False
        metadata["reason"] = (
            "query_timeout" if monotonic() >= deadline else "collection_failed"
        )
        code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
        if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            metadata["reason"] = "database_locked"
        elif code == sqlite3.SQLITE_INTERRUPT:
            metadata["reason"] = "query_timeout"
        # 不把可能含用户路径的异常文本放入反馈附件。
        metadata["error_type"] = type(exc).__name__
    return destination, metadata


def collect_feedback_records(
    db_path: Path, start: datetime, end: datetime, output: Path
) -> tuple[list[Path], dict]:
    """只查询现有数据库；查询缺失或失败不妨碍其他反馈附件。"""
    db_path, output = Path(db_path), Path(output)
    metadata = {
        "limits": {
            "rows_per_table": MAX_ROWS,
            "bytes_per_file": MAX_FILE_BYTES,
            "query_timeout_seconds_per_table": QUERY_TIMEOUT_SECONDS,
        },
        "requested_interval": {
            "start": start.astimezone().isoformat(timespec="seconds"),
            "end": end.astimezone().isoformat(timespec="seconds"),
        },
        "selection_note": (
            "仅查询所选本地时间范围，包含结束时间同一秒内的记录。"
            "first_time 和 last_time 保留数据库原始时间值。"
            "scan_complete 仅表示本次现有记录查询结束；空结果或扫描完成均不证明历史记录完整。"
            "缺失列不补造数据，未收集 saved_state、其他表或通用配置。"
        ),
        "tables": {},
    }
    paths = []
    for table, spec in _TABLES.items():
        path, table_metadata = _collect_table(db_path, table, spec, start, end, output)
        metadata["tables"][table] = table_metadata
        if path is not None:
            paths.append(path)
    return paths, metadata
