"""只读采集反馈生成时的专精状态，不还原问题发生时的状态。"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from time import monotonic

MAX_ROWS = 5000
MAX_FILE_BYTES = 1024 * 1024
MAX_FIELD_BYTES = 256 * 1024
QUERY_TIMEOUT_SECONDS = 2.0

_TABLES = {
    "mastery_plan": (
        "mastery_plans.jsonl",
        (
            "id",
            "char_id",
            "char_name",
            "skill_index",
            "skill_name",
            "target_level",
            "status",
            "failed_reason",
            "priority",
            "expires_at",
            "swap_frozen",
            "support_plan",
            "support_runtime",
            "created_at",
        ),
        ("priority", "id"),
    ),
    "mastery_route": (
        "mastery_routes.jsonl",
        ("profession", "supports", "is_default", "optimal", "half_off", "created_at"),
        ("profession", "is_default"),
    ),
}


def _now():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _table_metadata():
    return {
        "status": "unavailable",
        "file": None,
        "row_count": 0,
        "bytes": 0,
        "truncated": False,
        "scan_complete": False,
        "missing_columns": [],
        "omitted_value_count": 0,
        "omitted_columns": [],
        "first_key": None,
        "last_key": None,
        "reason": None,
    }


def _failure(metadata, exc, deadline):
    metadata.update(
        status="partial" if metadata["file"] is not None else "unavailable",
        truncated=metadata["file"] is not None,
        scan_complete=False,
        reason="query_timeout" if monotonic() >= deadline else "collection_failed",
        error_type=type(exc).__name__,
    )
    code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
    if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        metadata["reason"] = "database_locked"
    elif code == sqlite3.SQLITE_INTERRUPT:
        metadata["reason"] = "query_timeout"


def _collect_table(connection, table, spec, output, metadata):
    filename, columns, ordering = spec
    destination = None
    deadline = monotonic() + QUERY_TIMEOUT_SECONDS
    metadata["read_started_at"] = _now()
    try:
        connection.set_progress_handler(lambda: monotonic() >= deadline, 1000)
        connection.execute(
            f"PRAGMA busy_timeout = {max(0, int((deadline - monotonic()) * 1000))}"
        )
        if monotonic() >= deadline:
            metadata["reason"] = "query_timeout"
            return None
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            metadata["reason"] = "missing_table"
            return None
        available = {
            row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')
        }
        selected = [column for column in columns if column in available]
        metadata["missing_columns"] = [col for col in columns if col not in available]
        metadata["selected_columns"] = selected
        metadata["order_by"] = [column for column in ordering if column in available]
        if not selected:
            metadata["reason"] = "missing_columns"
            return None
        # 在 SQLite 内限制单字段读取量；BLOB 不进入 JSON，也不反序列化持久化对象。
        guards = [
            f"(typeof(\"{col}\") = 'blob' OR "
            f'length(CAST("{col}" AS BLOB)) > {MAX_FIELD_BYTES})'
            for col in selected
        ]
        fields = ", ".join(
            f'CASE WHEN {guard} THEN NULL ELSE "{col}" END'
            for col, guard in zip(selected, guards)
        )
        order = ", ".join(f'"{col}"' for col in metadata["order_by"])
        cursor = connection.execute(
            f'SELECT {fields}, {", ".join(guards)} FROM "{table}"'
            + (f" ORDER BY {order}" if order else "")
            + " LIMIT ?",
            (MAX_ROWS + 1,),
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
                omitted = [
                    col for col, flag in zip(selected, row[len(selected) :]) if flag
                ]
                record = {
                    col: value
                    for col, value in zip(selected, row)
                    if col not in omitted
                }
                if omitted:
                    record["_omitted_fields"] = omitted
                data = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
                if metadata["bytes"] + len(data) > MAX_FILE_BYTES:
                    metadata.update(truncated=True, reason="byte_limit")
                    break
                stream.write(data)
                metadata["bytes"] += len(data)
                metadata["row_count"] += 1
                key = {
                    col: record[col] for col in metadata["order_by"] if col in record
                }
                if metadata["first_key"] is None:
                    metadata["first_key"] = key
                metadata["last_key"] = key
                if omitted:
                    metadata["omitted_value_count"] += len(omitted)
                    metadata["omitted_columns"] = sorted(
                        set(metadata["omitted_columns"]) | set(omitted)
                    )
                    metadata.update(truncated=True, reason="field_limit_or_blob")
            else:
                metadata["scan_complete"] = True
        if metadata["truncated"] or metadata["missing_columns"]:
            metadata["status"] = "partial"
        else:
            metadata["status"] = "exported" if metadata["row_count"] else "empty"
        if metadata["missing_columns"] and metadata["reason"] is None:
            metadata["reason"] = "missing_columns"
    except (sqlite3.Error, OSError, TypeError, ValueError) as exc:
        _failure(metadata, exc, deadline)
    finally:
        metadata["read_finished_at"] = _now()
    return destination


def collect_feedback_state(db_path: Path, output: Path) -> tuple[list[Path], dict]:
    """在同一只读事务中读取现有专项表，缺失或失败时返回明确元数据。"""
    db_path, output = Path(db_path), Path(output)
    metadata = {
        "collection_started_at": _now(),
        "current_snapshot_not_historical": True,
        "limits": {
            "rows_per_table": MAX_ROWS,
            "bytes_per_file": MAX_FILE_BYTES,
            "bytes_per_field": MAX_FIELD_BYTES,
            "query_timeout_seconds_per_table": QUERY_TIMEOUT_SECONDS,
        },
        "selection_note": (
            "这些表是反馈采集时同一 SQLite 只读事务中的当前快照，不代表问题发生时的状态。"
            "JSON 字段保留原始文本，不推算专精进度或补造缺失列。"
            "超预算字段和 BLOB 被省略，所在记录用 _omitted_fields 标明；"
            "scan_complete 只表示当前表扫描结束，不证明字段完整或历史完整。"
            "未收集 saved_state、pickle、其他表或通用凭据。"
        ),
        "tables": {table: _table_metadata() for table in _TABLES},
        "scheduler_runtime": {
            "status": "unavailable",
            "reason": "no_synchronized_snapshot",
            "missing": ["effective_backup_plans", "task_queue", "waiting_group_shifts"],
            "note": "没有可复用的无副作用同步快照，未跨线程读取调度器可变对象。",
        },
    }
    paths = []
    try:
        if not db_path.is_file():
            for info in metadata["tables"].values():
                info["reason"] = "missing_database"
            return paths, metadata
        with closing(
            sqlite3.connect(
                db_path.resolve().as_uri() + "?mode=ro",
                uri=True,
                timeout=QUERY_TIMEOUT_SECONDS,
            )
        ) as connection:
            connection.execute("PRAGMA query_only = ON")
            connection.execute("BEGIN")
            for table, spec in _TABLES.items():
                path = _collect_table(
                    connection, table, spec, output, metadata["tables"][table]
                )
                if path is not None:
                    paths.append(path)
    except (sqlite3.Error, OSError, TypeError, ValueError) as exc:
        for info in metadata["tables"].values():
            if info["reason"] is None and info["status"] == "unavailable":
                _failure(info, exc, float("inf"))
    finally:
        metadata["collection_finished_at"] = _now()
    return paths, metadata
