import json
import logging

MISSED_ORDER_SUMMARY_PROMPT = (
    "你是 Mower 漏单分析助手。"
    "请根据给你的 JSON 数据，用简洁、用户友好的中文 Markdown 输出。"
    "固定使用这些标题："
    "## 结论、## 关键时间、## 关键证据、## 建议。"
    "标题下使用短 bullet points。"
    "关键时间只允许使用 target_task_time、current_task_time、previous_task_time、detected_time。"
    "必须明确区分“已证实”和“推测”。"
    "只能从 candidate_reasons 中选择原因，不要编造新的根因。"
    "必须优先按时间顺序理解证据，明确区分任务时间和检测到漏单时间。"
    "如果提供了 run_order_delay_minutes 和 atomic_task_time，要把 atomic_task_time 视为更接近实际执行的原子时间。"
    "优先参考 atomic_log_window 和其中的 runtime_info_logs 来判断原因。"
    "如果 candidate_reasons 中存在 session_interrupted_during_run_order，且证据包含“等待跑单 X 秒”，优先按会话被打断、疑似顶号解释。"
    "这种判断不要求同时出现“退出游戏”；只要在原子时间附近出现“等待跑单 X 秒”，就可以支持该原因。"
    "不要因为看到 ERROR 就直接判断 execution_failed。"
    "漏单报警本身的 ERROR 只是检测信号，不等于根因；只有与任务执行链直接相关、且时间上成立的异常，才能支持 execution_failed。"
    "不要输出英文标题、英文字段名、英文原因代号。"
    "如果输入里出现 previous_task_not_found、scene_wait_timeout、execution_failed 这类代号，输出时必须翻译成中文。"
)

REASON_LABELS = {
    "previous_task_not_found": "未找到上一条同房间跑单任务",
    "session_interrupted_during_run_order": "跑单时会话被打断，疑似顶号",
    "scene_wait_timeout": "场景等待超时或卡住",
    "execution_failed": "任务执行异常",
    "task_time_not_refreshed": "任务时间未及时刷新",
    "task_skipped_or_cleared": "任务被跳过或被清除",
    "insufficient_evidence": "证据不足",
}

FIELD_LABELS = {
    "target_task_time": "目标任务时间",
    "current_task_time": "当前任务时间",
    "previous_task_time": "上一条任务时间",
    "detected_time": "检测到漏单时间",
    "candidate_reasons": "候选原因",
    "runtime_info_logs": "运行日志",
    "timeline_logs": "数据库时间线",
}


def _get_logger():
    try:
        from arknights_mower.utils.log import logger as project_logger

        return project_logger
    except Exception:
        return logging.getLogger(__name__)


def _log_debug_report(report: str):
    _get_logger().debug("[missed_order_report]\n%s", report.replace("<br/>", "\n"))


def _shorten(text, limit: int = 160) -> str:
    text = "" if text is None else str(text)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _reason_label(reason_type: str) -> str:
    return REASON_LABELS.get(reason_type, reason_type or "未知原因")


def _localize_candidate_reasons(reasons: list[dict]) -> list[dict]:
    localized = []
    for item in reasons or []:
        localized_item = dict(item)
        localized_item["type_label"] = _reason_label(item.get("type"))
        localized.append(localized_item)
    return localized


def _build_llm_payload(result: dict) -> dict:
    payload = json.loads(
        json.dumps(
            result.get("analysis_payload", result), ensure_ascii=False, default=str
        )
    )
    if isinstance(payload.get("candidate_reasons"), list):
        payload["candidate_reasons"] = _localize_candidate_reasons(
            payload["candidate_reasons"]
        )
    return payload


def _localize_summary_text(text: str) -> str:
    normalized = text or ""
    for source, target in REASON_LABELS.items():
        normalized = normalized.replace(source, target)
    for source, target in FIELD_LABELS.items():
        normalized = normalized.replace(source, target)
    return normalized


def _strip_runtime_prefix(message: str) -> str:
    text = "" if message is None else str(message)
    if len(text) >= 24 and text[:4].isdigit() and text[4] == "-":
        return text[24:].strip()
    return text.strip()


def _collapse_log_rows(rows: list[dict], *, runtime: bool) -> list[dict]:
    collapsed = []
    for row in rows:
        time_key = "time" if runtime else "log_local_time"
        message = row.get("message") or ""
        normalized = _strip_runtime_prefix(message) if runtime else message.strip()
        signature = (
            row.get("file") if runtime else row.get("level"),
            normalized,
        )
        if collapsed and collapsed[-1]["signature"] == signature:
            collapsed[-1]["hit_count"] += 1
            collapsed[-1]["end_time"] = row.get(time_key)
            continue
        collapsed.append(
            {
                "signature": signature,
                "file": row.get("file"),
                "level": row.get("level"),
                "message": normalized,
                "start_time": row.get(time_key),
                "end_time": row.get(time_key),
                "hit_count": 1,
            }
        )
    return collapsed


def _collapse_trace_entries(entries: list[dict]) -> list[dict]:
    collapsed = []
    for entry in entries:
        step = entry.get("step")
        if step not in {"runtime_info_log", "timeline_log"}:
            collapsed.append(entry)
            continue
        if step == "runtime_info_log":
            signature = (
                step,
                entry.get("file"),
                _strip_runtime_prefix(entry.get("message") or ""),
            )
            time_field = "time"
        else:
            signature = (
                step,
                entry.get("level"),
                entry.get("message") or "",
            )
            time_field = "log_local_time"
        if collapsed:
            prev = collapsed[-1]
            prev_signature = prev.get("_signature")
            if prev_signature == signature:
                prev["hit_count"] = prev.get("hit_count", 1) + 1
                prev["end_time"] = entry.get(time_field)
                continue
        merged = dict(entry)
        merged["_signature"] = signature
        merged["start_time"] = entry.get(time_field)
        merged["end_time"] = entry.get(time_field)
        merged["hit_count"] = 1
        collapsed.append(merged)
    for item in collapsed:
        item.pop("_signature", None)
    return collapsed


def _compact_log_rows(rows: list[dict], *, runtime: bool, limit: int) -> list[dict]:
    grouped_rows = _collapse_log_rows(rows, runtime=runtime)
    compacted = []
    for row in grouped_rows[:limit]:
        compacted.append(
            {
                "file": row.get("file"),
                "level": row.get("level"),
                "start_time": row.get("start_time"),
                "end_time": row.get("end_time"),
                "hit_count": row.get("hit_count"),
                "message": _shorten(row.get("message"), 240),
            }
        )
    return compacted


def _build_compact_analysis_payload(result: dict) -> dict:
    timeline_logs = result.get("timeline_logs") or []
    runtime_logs = (
        result.get("focused_runtime_info_logs") or result.get("runtime_info_logs") or []
    )
    return {
        "signal_type": result.get("signal_type"),
        "room": result.get("room") or result.get("candidate_room"),
        "target_task_time": result.get("target_task_time"),
        "current_task_time": result.get("current_task_time"),
        "previous_task_time": result.get("previous_task_time"),
        "detected_time": result.get("detected_time"),
        "run_order_delay_minutes": result.get("run_order_delay_minutes"),
        "atomic_task_time": result.get("atomic_task_time"),
        "db_query_window": result.get("db_query_window"),
        "runtime_window": result.get("runtime_window"),
        "atomic_log_window": result.get("atomic_log_window"),
        "candidate_reasons": result.get("candidate_reasons") or [],
        "timeline_log_count": len(timeline_logs),
        "runtime_log_count": len(runtime_logs),
        "timeline_logs": _compact_log_rows(timeline_logs, runtime=False, limit=24),
        "runtime_info_logs": _compact_log_rows(runtime_logs, runtime=True, limit=32),
    }


def _is_context_length_error(exc: Exception) -> bool:
    text = str(exc).lower()
    if "maximum context length" in text:
        return True
    if "context length" in text and "tokens" in text:
        return True
    if "requested" in text and "tokens" in text and "invalid_request_error" in text:
        return True
    return False


def format_missed_order_list(orders: list[dict]) -> str:
    lines = ["找到这些漏单日志，请回复编号或直接回复时间："]
    for item in orders:
        task_time = item.get("task_time") or "未锁定"
        room = item.get("room") or "未锁定"
        level = item.get("level") or "INFO"
        message = _shorten(item.get("message"), 80) or "漏单"
        line = (
            f"{item['index']}. 事件={item.get('log_local_time') or item.get('local_time')} | "
            f"任务={task_time} | 房间={room} | [{level}] {message}"
        )
        if (
            item.get("previous_task_time")
            and item.get("previous_task_time") != task_time
        ):
            line += f" | 上次任务={item.get('previous_task_time')}"
        lines.append(line)
    return "<br/>".join(lines)


def format_missed_order_task_records(result: dict) -> str:
    lines = ["任务追踪明细："]
    signal_type = result.get("signal_type") or result.get("analysis_mode") or "未知"
    lines.append(f"漏单类型：{signal_type}")
    lines.append(
        f"房间：{result.get('room') or result.get('candidate_room') or '未锁定'}"
    )
    lines.append(f"目标任务时间：{result.get('target_task_time') or '未锁定'}")
    lines.append(f"触发任务时间：{result.get('current_task_time') or '未锁定'}")
    lines.append(f"上一条任务时间：{result.get('previous_task_time') or '未锁定'}")
    lines.append(f"检测到漏单时间：{result.get('detected_time') or '未锁定'}")
    lines.append(f"跑单延时(分钟)：{result.get('run_order_delay_minutes')}")
    lines.append(f"原子执行时间：{result.get('atomic_task_time') or '未锁定'}")

    db_window = result.get("db_query_window") or {}
    if db_window:
        lines.append(
            f"数据库查询窗口(UTC)：{db_window.get('start')} -> {db_window.get('end')}"
        )
    runtime_window = result.get("runtime_window") or {}
    if runtime_window:
        lines.append(
            f"runtime 扫描范围：{runtime_window.get('start')} -> {runtime_window.get('end')}"
        )
    atomic_log_window = result.get("atomic_log_window") or {}
    if (
        atomic_log_window
        and atomic_log_window.get("start")
        and atomic_log_window.get("end")
    ):
        lines.append(
            f"原子时间聚焦范围：{atomic_log_window.get('start')} -> {atomic_log_window.get('end')}"
        )

    lines.append("数据库时间线：")
    timeline_logs = result.get("timeline_logs") or []
    if not timeline_logs:
        lines.append("无数据库时间线")
    else:
        grouped_timeline_logs = _collapse_log_rows(timeline_logs, runtime=False)
        lines.append(
            f"共 {len(timeline_logs)} 条，聚合后 {len(grouped_timeline_logs)} 组"
        )
        for index, row in enumerate(grouped_timeline_logs, start=1):
            time_span = row.get("start_time")
            if row.get("end_time") and row.get("end_time") != row.get("start_time"):
                time_span = f"{row.get('start_time')} -> {row.get('end_time')}"
            lines.append(
                f"{index}. [{time_span}] {row.get('level')} | "
                f"命中次数={row.get('hit_count')} | "
                f"内容={_shorten(row.get('message'), 160)}"
            )

    lines.append("日志文件命中：")
    runtime_files = result.get("runtime_log_files") or []
    if not runtime_files:
        lines.append("无命中文件")
    else:
        lines.extend(runtime_files)

    lines.append("日志文件摘录：")
    runtime_logs = (
        result.get("focused_runtime_info_logs") or result.get("runtime_info_logs") or []
    )
    if not runtime_logs:
        lines.append("无运行信息日志")
    else:
        grouped_runtime_logs = _collapse_log_rows(runtime_logs, runtime=True)
        lines.append(
            f"共 {len(runtime_logs)} 条，聚合后 {len(grouped_runtime_logs)} 组"
        )
        for index, row in enumerate(grouped_runtime_logs, start=1):
            time_span = row.get("start_time")
            if row.get("end_time") and row.get("end_time") != row.get("start_time"):
                time_span = f"{row.get('start_time')} -> {row.get('end_time')}"
            lines.append(
                f"{index}. [{time_span}] {row.get('file')} | "
                f"命中次数={row.get('hit_count')} | "
                f"{_shorten(row.get('message'), 220)}"
            )

    lines.append("候选原因：")
    reasons = result.get("candidate_reasons") or []
    if not reasons:
        lines.append("无候选原因")
    else:
        for index, item in enumerate(reasons, start=1):
            lines.append(
                f"{index}. {item.get('type_label') or _reason_label(item.get('type'))} | 置信提示={item.get('confidence_hint')} | "
                f"证据={_shorten(item.get('supported_evidence'), 120)}"
            )
    return "<br/>".join(lines)


def fallback_missed_order_summary(result: dict) -> str:
    reasons = result.get("candidate_reasons") or []
    top_reason = (
        _reason_label(reasons[0]["type"])
        if reasons
        else _reason_label("insufficient_evidence")
    )
    room = result.get("room") or result.get("candidate_room") or "未锁定"
    return (
        f"最可能原因：{top_reason}<br/>"
        f"目标任务时间：{result.get('target_task_time') or '未锁定'}<br/>"
        f"触发任务时间：{result.get('current_task_time') or '未锁定'}<br/>"
        f"上一条任务时间：{result.get('previous_task_time') or '未锁定'}<br/>"
        f"检测到漏单时间：{result.get('detected_time') or '未锁定'}<br/>"
        f"房间：{room}<br/>"
    )


def format_missed_order_report(result: dict, summary_text: str) -> str:
    summary_source = result.get("summary_source") or "unknown"
    source_label = {
        "llm": "大模型",
        "llm_compact_retry": "大模型压缩重试",
        "llm_fallback_content_empty": "大模型空结果回退",
        "llm_compact_retry_fallback_content_empty": "大模型压缩重试后回退",
        "fallback_no_llm": "未启用大模型，使用规则回退",
        "fallback_on_error": "大模型出错，使用规则回退",
    }.get(summary_source, summary_source)
    sections = [f"分析结论：\n来源：{source_label}\n{summary_text}"]
    sections.append(format_missed_order_task_records(result))
    report = "<br/><br/>".join(section for section in sections if section)
    _log_debug_report(report)
    return report


def summarize_missed_order_result(result: dict, llm=None) -> str:
    if llm is None:
        summary = fallback_missed_order_summary(result)
        result["summary_source"] = "fallback_no_llm"
        trace = result.setdefault("analysis_trace", [])
        trace.append(
            {
                "step": "llm_summary_skipped",
                "reason": "llm_unavailable",
                "summary_preview": _shorten(summary, 160),
            }
        )
        return format_missed_order_report(result, summary)
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        payload = _build_llm_payload(result)
        response = llm.invoke(
            [
                SystemMessage(content=MISSED_ORDER_SUMMARY_PROMPT),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ]
        )
        content = response.content if hasattr(response, "content") else ""
        summary = (
            _localize_summary_text(content)
            if content
            else fallback_missed_order_summary(result)
        )
        result["summary_source"] = "llm" if content else "llm_fallback_content_empty"
        trace = result.setdefault("analysis_trace", [])
        trace.append(
            {
                "step": "llm_summary_generated",
                "used_fallback": not bool(content),
                "summary_preview": _shorten(summary, 160),
            }
        )
        return format_missed_order_report(result, summary)
    except Exception as exc:
        if llm is not None and _is_context_length_error(exc):
            trace = result.setdefault("analysis_trace", [])
            compact_payload = _build_compact_analysis_payload(result)
            if isinstance(compact_payload.get("candidate_reasons"), list):
                compact_payload["candidate_reasons"] = _localize_candidate_reasons(
                    compact_payload["candidate_reasons"]
                )
            trace.append(
                {
                    "step": "llm_summary_compact_retry",
                    "reason": "context_length_exceeded",
                    "timeline_log_count": compact_payload.get("timeline_log_count"),
                    "runtime_log_count": compact_payload.get("runtime_log_count"),
                }
            )
            try:
                from langchain_core.messages import HumanMessage, SystemMessage

                response = llm.invoke(
                    [
                        SystemMessage(content=MISSED_ORDER_SUMMARY_PROMPT),
                        HumanMessage(
                            content=json.dumps(compact_payload, ensure_ascii=False)
                        ),
                    ]
                )
                content = response.content if hasattr(response, "content") else ""
                summary = (
                    _localize_summary_text(content)
                    if content
                    else fallback_missed_order_summary(result)
                )
                result["summary_source"] = (
                    "llm_compact_retry"
                    if content
                    else "llm_compact_retry_fallback_content_empty"
                )
                trace.append(
                    {
                        "step": "llm_summary_generated",
                        "path": "compact_retry",
                        "used_fallback": not bool(content),
                        "summary_preview": _shorten(summary, 160),
                    }
                )
                return format_missed_order_report(result, summary)
            except Exception as retry_exc:
                _get_logger().exception(retry_exc)
                exc = retry_exc
        else:
            _get_logger().exception(exc)
        summary = fallback_missed_order_summary(result)
        result["summary_source"] = "fallback_on_error"
        trace = result.setdefault("analysis_trace", [])
        trace.append(
            {
                "step": "llm_summary_failed",
                "error": str(exc),
                "summary_preview": _shorten(summary, 160),
            }
        )
        return format_missed_order_report(result, summary)
