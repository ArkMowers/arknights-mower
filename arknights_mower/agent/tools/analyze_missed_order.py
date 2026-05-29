import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from arknights_mower.utils.path import get_path

LIST_ORDERS_MODE = "list_orders"
ANALYZE_BY_ORDER_MODE = "analyze_by_order"
ANALYZE_BY_TIME_MODE = "analyze_by_time"
ANALYZE_MISSED_ORDER_MODES = (
    LIST_ORDERS_MODE,
    ANALYZE_BY_ORDER_MODE,
    ANALYZE_BY_TIME_MODE,
)

CURRENT_ORDER_MISS_KEYWORD = "检测到漏单"
PREVIOUS_ORDER_MISS_KEYWORD = "检测到上一个订单漏单"
WAIT_HINT_KEYWORDS = ("等待", "超时", "Scene 9998", "卡住", "stuck", "timeout")
CLEAR_HINT_KEYWORDS = ("移除超过", "刷新时间")
RUN_ORDER_WAIT_HINT_KEYWORDS = "等待跑单"
SESSION_INTERRUPT_HINT_KEYWORDS = (
    "Scene.UNKNOWN",
    "unknown scene",
    "back_to_infrastructure",
    "退出游戏",
)
RUN_ORDER_WAIT_SECONDS_RE = re.compile(r"等待跑单\s*\d+(?:\.\d+)?\s*秒")
SCHEDULER_TASK_RE = re.compile(
    r"SchedulerTask\(time='(?P<time>[^']+)',task_plan=.*?,task_type=TaskTypes\."
    r"(?P<task_type>\w+),meta_data='(?P<meta_data>[^']*)'(?:,adjusted="
    r"(?P<adjusted>True|False))?\)",
    re.DOTALL,
)
RUNTIME_LOG_TIME_RE = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:,\d+)?\s"
)
RUNTIME_LOG_LEVEL_RE = re.compile(r"\b(?P<level>INFO)\b")


def _get_logger():
    try:
        from arknights_mower.utils.log import logger as project_logger

        return project_logger
    except Exception:
        return logging.getLogger(__name__)


def _get_run_order_delay_minutes() -> float:
    try:
        from arknights_mower.utils import config

        return float(getattr(config.conf, "run_order_delay", 0) or 0)
    except Exception:
        try:
            conf_path = get_path("@app/conf.yml")
            with conf_path.open("r", encoding="utf-8", errors="ignore") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("run_order_delay:"):
                        return float(line.split(":", 1)[1].strip())
        except Exception:
            pass
        return 0.0


def _trace(trace: list[dict], step: str, **details):
    entry = {"step": step, **details}
    trace.append(entry)
    _get_logger().debug(
        "[missed_order_trace] %s",
        json.dumps(entry, ensure_ascii=False, default=str),
    )
    return entry


def _database_path():
    return get_path("@app/tmp/data.db")


def _connect(database_path=None):
    return sqlite3.connect(database_path or _database_path())


def _parse_local_time(time_str: str) -> datetime:
    time_str = (time_str or "").strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析时间: {time_str}")


def _parse_scheduler_time(time_str: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue
    return None


def _classify_signal_type(level: str, message: str) -> str:
    text = message or ""
    if PREVIOUS_ORDER_MISS_KEYWORD in text and (level or "").upper() == "ERROR":
        return "previous_order_miss"
    if CURRENT_ORDER_MISS_KEYWORD in text:
        return "current_task_miss"
    return "generic_miss"


def _serialize_db_row(row: dict) -> dict:
    return {
        "log_utc_time": row.get("log_utc_time"),
        "log_local_time": row.get("log_local_time"),
        "level": row.get("level"),
        "task": row.get("task"),
        "message": row.get("message"),
    }


def _serialize_run_order(task: Optional[dict]) -> Optional[dict]:
    if not task:
        return None
    return {
        "task_time": task.get("task_time"),
        "room": task.get("room"),
        "adjusted": task.get("adjusted"),
        "log_local_time": task.get("log_local_time"),
        "log_utc_time": task.get("log_utc_time"),
    }


def fetch_logs_by_utc_window(
    start_ts: int, end_ts: int, database_path=None
) -> list[dict]:
    conn = _connect(database_path)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT
                time,
                strftime('%Y-%m-%d %H:%M:%S', time, 'unixepoch', 'localtime') AS local_time,
                task,
                level,
                message
            FROM log
            WHERE time BETWEEN ? AND ?
            ORDER BY time ASC
            """,
            (start_ts, end_ts),
        )
        rows = cursor.fetchall()
        return [
            {
                "log_utc_time": row[0],
                "log_local_time": row[1],
                "task": row[2] or "",
                "level": row[3] or "",
                "message": row[4] or "",
            }
            for row in rows
        ]
    finally:
        cursor.close()
        conn.close()


def fetch_missed_event_rows(limit: int = 10, database_path=None) -> list[dict]:
    conn = _connect(database_path)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT
                time,
                strftime('%Y-%m-%d %H:%M:%S', time, 'unixepoch', 'localtime') AS local_time,
                level,
                task,
                message
            FROM log
            WHERE message LIKE '%漏单%'
            ORDER BY time DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [
            {
                "log_utc_time": row[0],
                "log_local_time": row[1],
                "level": row[2] or "",
                "task": row[3] or "",
                "message": row[4] or "",
            }
            for row in rows
        ]
    finally:
        cursor.close()
        conn.close()


def extract_scheduler_tasks(
    text: str, log_local_time: Optional[str] = None
) -> list[dict]:
    if not text:
        return []
    tasks = []
    for match in SCHEDULER_TASK_RE.finditer(text):
        planned_at = _parse_scheduler_time(match.group("time"))
        if planned_at is None:
            continue
        tasks.append(
            {
                "task_time": planned_at.strftime("%Y-%m-%d %H:%M:%S"),
                "planned_at": planned_at,
                "task_type": match.group("task_type"),
                "room": match.group("meta_data"),
                "adjusted": match.group("adjusted") == "True",
                "log_local_time": log_local_time,
            }
        )
    return tasks


def extract_run_order_tasks(log_rows: list[dict]) -> list[dict]:
    tasks = []
    for row in log_rows:
        for task in extract_scheduler_tasks(
            row.get("task", ""), row.get("log_local_time")
        ):
            if task["task_type"] != "RUN_ORDER":
                continue
            tasks.append(
                {
                    **task,
                    "log_utc_time": row.get("log_utc_time"),
                    "level": row.get("level"),
                }
            )
    tasks.sort(key=lambda item: (item["planned_at"], item["log_utc_time"] or 0))
    return tasks


def select_latest_run_order_before_log_time(
    anchor_utc_time: int, run_orders: list[dict]
) -> Optional[dict]:
    eligible = [
        item
        for item in run_orders
        if item.get("log_utc_time") is not None
        and item["log_utc_time"] < anchor_utc_time
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda item: (item["log_utc_time"] or 0, item["planned_at"]))
    return eligible[-1]


def find_previous_same_room_task(
    current_task: Optional[dict], run_orders: list[dict]
) -> Optional[dict]:
    if current_task is None:
        return None
    lower_bound = current_task["planned_at"] - timedelta(hours=2.5)
    upper_bound = current_task["planned_at"] - timedelta(minutes=30)
    eligible = [
        item
        for item in run_orders
        if item["room"] == current_task["room"]
        and lower_bound <= item["planned_at"] <= upper_bound
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda item: (item["planned_at"], item["log_utc_time"] or 0))
    return eligible[-1]


def scan_runtime_info_logs(start_time: datetime, end_time: datetime) -> dict:
    try:
        folder = get_path("@app/log")
        wanted_suffixes = set()
        cursor_time = (start_time - timedelta(hours=1)).replace(
            minute=0, second=0, microsecond=0
        )
        end_hour = end_time.replace(minute=0, second=0, microsecond=0)
        while cursor_time <= end_hour:
            wanted_suffixes.add(cursor_time.strftime("%Y-%m-%d_%H"))
            cursor_time += timedelta(hours=1)
        files = []
        for file_path in sorted(folder.iterdir()):
            if file_path.is_file() and any(
                suffix in file_path.name for suffix in wanted_suffixes
            ):
                files.append(file_path)
        entries = []
        file_names = []
        for file_path in files:
            matched = False
            with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
                for raw_line in handle:
                    time_match = RUNTIME_LOG_TIME_RE.match(raw_line)
                    if not time_match:
                        continue
                    line_time = datetime.strptime(
                        time_match.group("time"), "%Y-%m-%d %H:%M:%S"
                    )
                    if not (start_time <= line_time <= end_time):
                        continue
                    level_match = RUNTIME_LOG_LEVEL_RE.search(raw_line)
                    if not level_match:
                        continue
                    matched = True
                    entries.append(
                        {
                            "time": line_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "file": file_path.name,
                            "message": raw_line.strip(),
                        }
                    )
            if matched:
                file_names.append(file_path.name)
        return {"files": file_names, "entries": entries}
    except Exception as exc:
        return {"files": [], "entries": [], "error": str(exc)}


def find_runtime_detected_time(runtime_info_logs: list[dict]) -> Optional[str]:
    for entry in runtime_info_logs:
        message = entry.get("message") or ""
        if (
            CURRENT_ORDER_MISS_KEYWORD in message
            or PREVIOUS_ORDER_MISS_KEYWORD in message
        ):
            return entry.get("time")
    return None


def _filter_runtime_logs_by_window(
    runtime_info_logs: list[dict], start_time: datetime, end_time: datetime
) -> list[dict]:
    filtered = []
    for row in runtime_info_logs:
        row_time = row.get("time")
        if not row_time:
            continue
        try:
            parsed = _parse_local_time(row_time)
        except Exception:
            continue
        if start_time <= parsed <= end_time:
            filtered.append(row)
    return filtered


def _parse_runtime_log_time(entry: dict) -> Optional[datetime]:
    row_time = entry.get("time")
    if not row_time:
        return None
    try:
        return _parse_local_time(row_time)
    except Exception:
        return None


def _find_session_interrupt_context(
    runtime_info_logs: list[dict],
) -> tuple[Optional[dict], bool]:
    wait_entry = None
    interrupt_confirmed = False
    for entry in runtime_info_logs:
        message = entry.get("message") or ""
        if not all(
            keyword in message for keyword in (RUN_ORDER_WAIT_HINT_KEYWORDS[0], "秒")
        ):
            continue
        if not RUN_ORDER_WAIT_SECONDS_RE.search(message):
            continue
        wait_entry = entry
        wait_time = _parse_runtime_log_time(entry)
        if wait_time is None:
            break
        for sibling in runtime_info_logs:
            if sibling is entry:
                continue
            sibling_message = sibling.get("message") or ""
            sibling_time = _parse_runtime_log_time(sibling)
            if sibling_time is None:
                continue
            delta_seconds = (sibling_time - wait_time).total_seconds()
            if abs(delta_seconds) <= 5 and any(
                keyword in sibling_message
                for keyword in ("Scene.UNKNOWN", "unknown scene")
            ):
                interrupt_confirmed = True
                break
            if 0 <= delta_seconds <= 60 and any(
                keyword in sibling_message
                for keyword in ("back_to_infrastructure", "退出游戏")
            ):
                interrupt_confirmed = True
                break
        break
    return wait_entry, interrupt_confirmed


def _scan_runtime_window(
    start_time: datetime,
    end_time: datetime,
    trace: Optional[list[dict]] = None,
    trace_step_prefix: str = "runtime_info",
):
    trace = trace if trace is not None else []
    runtime_result = scan_runtime_info_logs(start_time, end_time)
    runtime_info_logs = runtime_result.get("entries") or []
    _trace(
        trace,
        f"{trace_step_prefix}_logs_loaded",
        start=start_time.strftime("%Y-%m-%d %H:%M:%S"),
        end=end_time.strftime("%Y-%m-%d %H:%M:%S"),
        files=runtime_result.get("files") or [],
        count=len(runtime_info_logs),
        error=runtime_result.get("error"),
    )
    for index, row in enumerate(runtime_info_logs, start=1):
        _trace(
            trace,
            f"{trace_step_prefix}_log",
            index=index,
            time=row.get("time"),
            file=row.get("file"),
            message=(row.get("message") or "")[:220],
        )
    return runtime_result, runtime_info_logs


def build_candidate_reasons(
    signal_type: str,
    timeline_logs: list[dict],
    runtime_info_logs: list[dict],
    target_task: Optional[dict],
    previous_task_found: bool = True,
) -> list[dict]:
    timeline_text = " ".join(
        f"{row.get('task', '')} {row.get('message', '')}" for row in timeline_logs
    )
    runtime_text = " ".join(entry.get("message", "") for entry in runtime_info_logs)
    reasons = []
    wait_entry, interrupt_confirmed = _find_session_interrupt_context(runtime_info_logs)
    if wait_entry is not None:
        wait_message = wait_entry.get("message") or ""
        supported_evidence = [
            f"原子时间附近出现等待跑单日志：{wait_message[:160]}",
        ]
        if interrupt_confirmed:
            supported_evidence.append(
                "等待跑单日志前后存在场景异常/回基建/退出游戏线索"
            )
        reasons.append(
            {
                "type": "session_interrupted_during_run_order",
                "supported_evidence": supported_evidence,
                "contradicting_evidence": [],
                "confidence_hint": "high" if interrupt_confirmed else "medium",
            }
        )
    if signal_type == "previous_order_miss" and not previous_task_found:
        reasons.append(
            {
                "type": "previous_task_not_found",
                "supported_evidence": ["未找到上一条同房间 RUN_ORDER 任务"],
                "contradicting_evidence": [],
                "confidence_hint": "high",
            }
        )
    if any(keyword in runtime_text for keyword in WAIT_HINT_KEYWORDS):
        reasons.append(
            {
                "type": "scene_wait_timeout",
                "supported_evidence": [
                    "原子时间附近的 runtime INFO 日志中出现等待/超时/Scene 9998 线索"
                ],
                "contradicting_evidence": [],
                "confidence_hint": "medium",
            }
        )
    error_logs = [row for row in timeline_logs if row.get("level") == "ERROR"]
    actionable_error_logs = [
        row
        for row in error_logs
        if CURRENT_ORDER_MISS_KEYWORD not in (row.get("message") or "")
        and PREVIOUS_ORDER_MISS_KEYWORD not in (row.get("message") or "")
    ]
    if actionable_error_logs:
        reasons.append(
            {
                "type": "execution_failed",
                "supported_evidence": ["数据库时间线中存在与漏单报警不同的 ERROR 日志"],
                "contradicting_evidence": [],
                "confidence_hint": "medium",
            }
        )
    if any(keyword in timeline_text for keyword in CLEAR_HINT_KEYWORDS):
        reasons.append(
            {
                "type": "task_cleared_or_refreshed_but_not_executed",
                "supported_evidence": ["数据库时间线中存在清除/刷新/移除任务线索"],
                "contradicting_evidence": [],
                "confidence_hint": "low",
            }
        )
    if target_task and not error_logs and not runtime_info_logs:
        reasons.append(
            {
                "type": "task_time_not_refreshed",
                "supported_evidence": ["找到任务时间，但窗口内缺少支撑执行链路的日志"],
                "contradicting_evidence": [],
                "confidence_hint": "low",
            }
        )
    if not reasons:
        reasons.append(
            {
                "type": "insufficient_evidence",
                "supported_evidence": ["现有日志不足以闭环判断"],
                "contradicting_evidence": [],
                "confidence_hint": "low",
            }
        )
    return reasons


def resolve_event_context(
    event_row: dict, database_path=None, trace: Optional[list[dict]] = None
) -> dict:
    trace = trace if trace is not None else []
    signal_type = _classify_signal_type(
        event_row.get("level"), event_row.get("message")
    )
    event_utc_time = int(event_row["log_utc_time"])
    event_local_time = event_row["log_local_time"]
    _trace(
        trace,
        "selected_signal",
        signal_type=signal_type,
        log_utc_time=event_utc_time,
        log_local_time=event_local_time,
        level=event_row.get("level"),
        message=(event_row.get("message") or "")[:160],
    )
    _trace(
        trace,
        "db_query_window",
        start=event_utc_time - 1800,
        end=event_utc_time,
    )
    db_rows = fetch_logs_by_utc_window(
        event_utc_time - 1800, event_utc_time, database_path
    )
    run_orders = extract_run_order_tasks(db_rows)
    _trace(
        trace,
        "timeline_logs_loaded",
        count=len(db_rows),
        run_order_count=len(run_orders),
    )
    for index, row in enumerate(db_rows[:20], start=1):
        _trace(
            trace,
            "timeline_log",
            index=index,
            log_local_time=row.get("log_local_time"),
            level=row.get("level"),
            message=(row.get("message") or "")[:160],
        )
    current_task = select_latest_run_order_before_log_time(event_utc_time, run_orders)
    previous_task = None
    target_task = None
    if signal_type == "previous_order_miss":
        previous_task = find_previous_same_room_task(current_task, run_orders)
        target_task = previous_task
    else:
        target_task = current_task
        previous_task = find_previous_same_room_task(current_task, run_orders)
    _trace(
        trace,
        "resolved_event_context",
        signal_type=signal_type,
        event_local_time=event_local_time,
        target_task_time=target_task.get("task_time") if target_task else None,
        current_task_time=current_task.get("task_time") if current_task else None,
        previous_task_time=previous_task.get("task_time") if previous_task else None,
        room=(target_task or current_task or {}).get("room"),
    )
    return {
        "signal_type": signal_type,
        "event_row": event_row,
        "db_rows": db_rows,
        "run_orders": run_orders,
        "target_task": target_task,
        "current_task": current_task,
        "previous_task": previous_task,
        "room": (target_task or current_task or {}).get("room"),
    }


def build_analysis_result(context: dict, trace: Optional[list[dict]] = None) -> dict:
    trace = trace if trace is not None else []
    signal_type = context["signal_type"]
    event_row = context["event_row"]
    target_task = context["target_task"]
    current_task = context["current_task"]
    previous_task = context["previous_task"]
    room = context["room"]
    run_order_delay_minutes = _get_run_order_delay_minutes()
    atomic_task_dt = None
    atomic_window_start = None
    atomic_window_end = None
    runtime_start = None
    probe_end = None
    runtime_end = None
    runtime_result = {"files": []}
    runtime_info_logs = []
    focused_runtime_info_logs = []
    detected_time = None
    if signal_type == "current_task_miss":
        if target_task is None:
            raise ValueError("未找到当前漏单对应的 RUN_ORDER 任务")
        runtime_start = target_task["planned_at"] - timedelta(minutes=5)
        probe_end = target_task["planned_at"] + timedelta(minutes=30)
    elif signal_type == "previous_order_miss":
        if target_task is None:
            detected_time = event_row["log_local_time"]
            _trace(
                trace,
                "runtime_scan_skipped",
                signal_type=signal_type,
                reason="target_task_not_found",
                detected_time=detected_time,
            )
        else:
            runtime_start = target_task["planned_at"] - timedelta(minutes=5)
            probe_end = target_task["planned_at"] + timedelta(minutes=5)
    else:
        if target_task is None:
            raise ValueError("未找到漏单对应的 RUN_ORDER 任务")
        runtime_start = target_task["planned_at"] - timedelta(minutes=5)
        probe_end = target_task["planned_at"] + timedelta(minutes=30)

    if runtime_start is not None and probe_end is not None:
        runtime_result, runtime_info_logs = _scan_runtime_window(
            runtime_start, probe_end, trace=trace, trace_step_prefix="runtime_probe"
        )
        detected_time = find_runtime_detected_time(runtime_info_logs)
        runtime_end = probe_end
        if detected_time:
            detected_dt = _parse_local_time(detected_time)
            if detected_dt >= runtime_start:
                runtime_end = detected_dt
        elif signal_type in {"current_task_miss", "generic_miss"}:
            detected_time = target_task.get("task_time") if target_task else None
        else:
            detected_time = event_row["log_local_time"]
        runtime_result, runtime_info_logs = _scan_runtime_window(
            runtime_start, runtime_end, trace=trace, trace_step_prefix="runtime_info"
        )
        focused_runtime_info_logs = runtime_info_logs
    if runtime_start is not None and target_task is not None:
        atomic_task_dt = target_task["planned_at"] + timedelta(
            minutes=run_order_delay_minutes
        )
        atomic_window_start = atomic_task_dt - timedelta(minutes=1)
        atomic_window_end = atomic_task_dt + timedelta(minutes=1)
        _trace(
            trace,
            "task_execution_anchor",
            task_time=target_task.get("task_time"),
            run_order_delay_minutes=run_order_delay_minutes,
            atomic_task_time=atomic_task_dt.strftime("%Y-%m-%d %H:%M:%S"),
            atomic_window_start=atomic_window_start.strftime("%Y-%m-%d %H:%M:%S"),
            atomic_window_end=atomic_window_end.strftime("%Y-%m-%d %H:%M:%S"),
        )
        focused_runtime_info_logs = _filter_runtime_logs_by_window(
            runtime_info_logs, atomic_window_start, atomic_window_end
        )
        _trace(
            trace,
            "runtime_atomic_focus",
            source_count=len(runtime_info_logs),
            focused_count=len(focused_runtime_info_logs),
            atomic_task_time=atomic_task_dt.strftime("%Y-%m-%d %H:%M:%S"),
            atomic_window_start=atomic_window_start.strftime("%Y-%m-%d %H:%M:%S"),
            atomic_window_end=atomic_window_end.strftime("%Y-%m-%d %H:%M:%S"),
        )
        for index, row in enumerate(focused_runtime_info_logs, start=1):
            _trace(
                trace,
                "runtime_atomic_log",
                index=index,
                time=row.get("time"),
                file=row.get("file"),
                message=(row.get("message") or "")[:220],
            )
    candidate_reasons = build_candidate_reasons(
        signal_type,
        context["db_rows"],
        focused_runtime_info_logs,
        target_task,
        previous_task_found=signal_type != "previous_order_miss"
        or previous_task is not None,
    )
    for index, item in enumerate(candidate_reasons, start=1):
        _trace(
            trace,
            "rule_candidate_reason",
            index=index,
            type=item.get("type"),
            confidence_hint=item.get("confidence_hint"),
            supported_evidence=item.get("supported_evidence"),
            contradicting_evidence=item.get("contradicting_evidence"),
        )
    return {
        "signal_type": signal_type,
        "analysis_mode": signal_type,
        "log_utc_time": event_row["log_utc_time"],
        "log_local_time": event_row["log_local_time"],
        "detected_time": detected_time,
        "room": room,
        "candidate_room": room,
        "run_order_delay_minutes": run_order_delay_minutes,
        "atomic_task_time": atomic_task_dt.strftime("%Y-%m-%d %H:%M:%S")
        if atomic_task_dt
        else None,
        "target_task_time": target_task.get("task_time") if target_task else None,
        "current_task_time": current_task.get("task_time") if current_task else None,
        "previous_task_time": previous_task.get("task_time") if previous_task else None,
        "db_query_window": {
            "start": event_row["log_utc_time"] - 1800,
            "end": event_row["log_utc_time"],
        },
        "runtime_window": (
            {
                "start": runtime_start.strftime("%Y-%m-%d %H:%M:%S"),
                "end": runtime_end.strftime("%Y-%m-%d %H:%M:%S"),
            }
            if runtime_start is not None and runtime_end is not None
            else None
        ),
        "atomic_log_window": {
            "start": atomic_window_start.strftime("%Y-%m-%d %H:%M:%S")
            if atomic_window_start
            else None,
            "end": atomic_window_end.strftime("%Y-%m-%d %H:%M:%S")
            if atomic_window_end
            else None,
        },
        "timeline_logs": [_serialize_db_row(row) for row in context["db_rows"]],
        "runtime_log_files": runtime_result.get("files") or [],
        "runtime_info_logs": runtime_info_logs,
        "focused_runtime_info_logs": focused_runtime_info_logs,
        "candidate_reasons": candidate_reasons,
        "run_order_task": _serialize_run_order(target_task),
        "current_run_order_task": _serialize_run_order(current_task),
        "previous_run_order_task": _serialize_run_order(previous_task),
        "analysis_trace": trace,
        "analysis_payload": {
            "signal_type": signal_type,
            "log_utc_time": event_row["log_utc_time"],
            "log_local_time": event_row["log_local_time"],
            "detected_time": detected_time,
            "room": room,
            "run_order_delay_minutes": run_order_delay_minutes,
            "atomic_task_time": atomic_task_dt.strftime("%Y-%m-%d %H:%M:%S")
            if atomic_task_dt
            else None,
            "target_task_time": target_task.get("task_time") if target_task else None,
            "current_task_time": current_task.get("task_time")
            if current_task
            else None,
            "previous_task_time": previous_task.get("task_time")
            if previous_task
            else None,
            "atomic_log_window": {
                "start": atomic_window_start.strftime("%Y-%m-%d %H:%M:%S")
                if atomic_window_start
                else None,
                "end": atomic_window_end.strftime("%Y-%m-%d %H:%M:%S")
                if atomic_window_end
                else None,
            },
            "timeline_logs": [
                {
                    "time": row["log_local_time"],
                    "level": row["level"],
                    "message": row["message"][:300],
                }
                for row in context["db_rows"]
            ],
            "runtime_info_logs": focused_runtime_info_logs,
            "candidate_reasons": candidate_reasons,
        },
    }


def list_missed_orders_payload(limit: int = 10, database_path=None) -> dict:
    trace = []
    _trace(trace, "list_orders_started", limit=limit)
    event_rows = fetch_missed_event_rows(limit=limit, database_path=database_path)
    orders = []
    for index, event_row in enumerate(event_rows, start=1):
        context = resolve_event_context(
            event_row, database_path=database_path, trace=trace
        )
        item = {
            "index": index,
            "log_utc_time": event_row["log_utc_time"],
            "event_utc_time": event_row["log_utc_time"],
            "local_time": event_row["log_local_time"],
            "log_local_time": event_row["log_local_time"],
            "level": event_row["level"],
            "message": event_row["message"],
            "signal_type": context["signal_type"],
            "task_time": context["target_task"].get("task_time")
            if context["target_task"]
            else None,
            "room": context["room"],
            "current_task_time": context["current_task"].get("task_time")
            if context["current_task"]
            else None,
            "previous_task_time": context["previous_task"].get("task_time")
            if context["previous_task"]
            else None,
        }
        orders.append(item)
        _trace(
            trace,
            "missed_order_item",
            index=index,
            log_local_time=item["log_local_time"],
            signal_type=item["signal_type"],
            task_time=item["task_time"],
            room=item["room"],
        )
    _trace(trace, "list_orders_loaded", count=len(orders))
    return {
        "has_orders": bool(orders),
        "count": len(orders),
        "orders": orders,
        "analysis_trace": trace,
    }


def find_matching_event_by_time(
    query_time: str, database_path=None, trace: Optional[list[dict]] = None
) -> Optional[dict]:
    trace = trace if trace is not None else []
    query_dt = _parse_local_time(query_time)
    candidate_rows = fetch_missed_event_rows(limit=20, database_path=database_path)
    scored = []
    for row in candidate_rows:
        context = resolve_event_context(row, database_path=database_path, trace=trace)
        target_task_time = (
            context["target_task"].get("task_time") if context["target_task"] else None
        )
        task_distance = float("inf")
        if target_task_time:
            task_distance = abs(
                (_parse_local_time(target_task_time) - query_dt).total_seconds()
            )
        event_distance = abs(
            (_parse_local_time(row["log_local_time"]) - query_dt).total_seconds()
        )
        if min(task_distance, event_distance) > 300:
            continue
        scored.append(
            (
                task_distance,
                event_distance,
                0 if context["signal_type"] != "generic_miss" else 1,
                row,
            )
        )
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    selected = scored[0][3]
    _trace(
        trace,
        "matched_event_by_time",
        query_time=query_time,
        matched_log_local_time=selected["log_local_time"],
        matched_log_utc_time=selected["log_utc_time"],
    )
    return selected


def analyze_missed_order_by_order(
    order_time: str,
    window_start_hours: float = 0.5,
    window_end_hours: float = 0.0,
    signal_type: Optional[str] = None,
    log_event_time: Optional[str] = None,
    log_event_ts: Optional[int] = None,
    room: Optional[str] = None,
    database_path=None,
) -> dict:
    trace = []
    _trace(
        trace,
        "analyze_by_order_started",
        order_time=order_time,
        signal_type=signal_type,
        log_event_time=log_event_time,
        log_event_ts=log_event_ts,
        room=room,
    )
    event_row = None
    candidate_rows = fetch_missed_event_rows(limit=20, database_path=database_path)
    if log_event_ts is not None:
        event_row = next(
            (row for row in candidate_rows if row["log_utc_time"] == int(log_event_ts)),
            None,
        )
    if event_row is None and log_event_time:
        event_row = next(
            (row for row in candidate_rows if row["log_local_time"] == log_event_time),
            None,
        )
    if event_row is None:
        event_row = find_matching_event_by_time(
            order_time, database_path=database_path, trace=trace
        )
    if event_row is None:
        raise ValueError("未找到对应的漏单日志事件")
    context = resolve_event_context(event_row, database_path=database_path, trace=trace)
    if signal_type:
        context["signal_type"] = signal_type
    if room and not context["room"]:
        context["room"] = room
    return build_analysis_result(context, trace=trace)


def analyze_missed_order_by_time(
    event_time: str,
    window_start_hours: float = 0.5,
    window_end_hours: float = 0.0,
    database_path=None,
) -> dict:
    trace = []
    _trace(trace, "analyze_by_time_started", event_time=event_time)
    event_row = find_matching_event_by_time(
        event_time, database_path=database_path, trace=trace
    )
    if event_row is None:
        raise ValueError("未找到该时间附近的漏单日志")
    context = resolve_event_context(event_row, database_path=database_path, trace=trace)
    return build_analysis_result(context, trace=trace)


def _serialize_tool_result(mode: str, payload: dict) -> str:
    return json.dumps({"mode": mode, **payload}, ensure_ascii=False, default=str)


def analyze_missed_order(
    mode: str,
    order_time: Optional[str] = None,
    event_time: Optional[str] = None,
    window_start_hours: float = 0.5,
    window_end_hours: float = 0.0,
    signal_type: Optional[str] = None,
    log_event_time: Optional[str] = None,
    log_event_ts: Optional[int] = None,
    room: Optional[str] = None,
) -> str:
    try:
        if mode == LIST_ORDERS_MODE:
            return _serialize_tool_result(mode, list_missed_orders_payload())
        if mode == ANALYZE_BY_ORDER_MODE:
            if not order_time:
                raise ValueError("analyze_by_order 需要 order_time")
            return _serialize_tool_result(
                mode,
                analyze_missed_order_by_order(
                    order_time=order_time,
                    window_start_hours=window_start_hours,
                    window_end_hours=window_end_hours,
                    signal_type=signal_type,
                    log_event_time=log_event_time,
                    log_event_ts=log_event_ts,
                    room=room,
                ),
            )
        if mode == ANALYZE_BY_TIME_MODE:
            if not event_time:
                raise ValueError("analyze_by_time 需要 event_time")
            return _serialize_tool_result(
                mode,
                analyze_missed_order_by_time(
                    event_time=event_time,
                    window_start_hours=window_start_hours,
                    window_end_hours=window_end_hours,
                ),
            )
        raise ValueError(f"未知 mode: {mode}")
    except Exception as exc:
        _get_logger().exception(exc)
        return json.dumps({"mode": mode, "error": str(exc)}, ensure_ascii=False)


analyze_missed_order_tool_def = {
    "type": "function",
    "function": {
        "name": "analyze_missed_order",
        "description": (
            "专门用于分析跑单漏单原因。"
            "list_orders 列出 log 表里的漏单日志；"
            "analyze_by_order 按选中的漏单日志分析；"
            "analyze_by_time 按用户给定时间先匹配漏单事件，再分析。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": list(ANALYZE_MISSED_ORDER_MODES),
                },
                "order_time": {"type": "string"},
                "event_time": {"type": "string"},
                "window_start_hours": {"type": "number"},
                "window_end_hours": {"type": "number"},
                "signal_type": {
                    "type": "string",
                    "enum": [
                        "current_task_miss",
                        "previous_order_miss",
                        "generic_miss",
                    ],
                },
                "log_event_time": {"type": "string"},
                "log_event_ts": {"type": "integer"},
                "room": {"type": "string"},
            },
            "required": ["mode"],
        },
    },
}
