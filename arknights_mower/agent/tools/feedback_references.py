"""从反馈附件建立有界原文引用，并校验分析所引用的附件记录。"""

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from arknights_mower.agent.tools.get_source_snippet import (
    _PROJECT_ROOT,
    _allowed_source_path,
)

MAX_BUNDLE_BYTES = 16 * 1024**2
MAX_SCAN_BYTES = 16 * 1024**2
MAX_SCAN_LINES = 100000
MAX_LOG_MEMBERS = 32
MAX_RECORDS = 48
MAX_RECORD_TEXT_BYTES = 1024
MAX_TEXT_BYTES = 48 * 1024
MAX_LINE_BYTES = 16 * 1024
MAX_SOURCE_FILES = 4
MAX_SOURCE_SCAN_BYTES = 2 * 1024**2
MAX_SOURCE_TEXT_BYTES = 24 * 1024
MAX_INDEX_BYTES = 96 * 1024
MAX_ESCAPED_INDEX_BYTES = 192 * 1024
MAX_SOURCE_OMISSIONS = 64
SOURCE_CONTEXT = 20
ANALYSIS_NOTE = "AI 对日志、历史记录、当前状态和源码的解释均为推断；当前状态不证明故障时状态，引用 ID 有效不证明解释正确，也不能自动证明故障根因。"
_LOG_START = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[,.]\d+)?) "
    r".*?\b(CRITICAL|ERROR|WARNING|INFO|DEBUG)\b"
)
_LOCATIONS = re.compile(
    r'File\s+["\']([^"\']+\.(?:py|js|ts|vue|java|cs))["\'],\s*line\s+(\d+)'
    r'|(?<![\w/\\])([^\s"\'<>]+\.(?:py|js|ts|vue|java|cs)):(\d+)'
)
_BUSINESS_DEBUG = re.compile(
    r"mastery|fiammetta|专精|菲亚梅塔|挂起|恢复|任务|调度|心情", re.I
)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _identity(*parts):
    return _digest(json.dumps(parts, ensure_ascii=False).encode("utf-8"))


def _priority(record):
    level = record["level"]
    if level in {"ERROR", "CRITICAL"}:
        rank = 0
    elif level == "WARNING":
        rank = 1
    elif record["kind"] in {"database_history", "current_snapshot"}:
        rank = 2
    elif level == "INFO":
        rank = 3
    elif level == "DEBUG" and _BUSINESS_DEBUG.search(record["text"]):
        rank = 4
    else:
        rank = 5
    return (0 if record.get("focus_matched") else 1), rank


def _selection_key(record):
    return _priority(record), record["_priority_order"], record["_order"]


def _reference_member(name):
    path = PurePosixPath(name)
    return (
        "\\" not in name
        and not path.is_absolute()
        and ".." not in path.parts
        and str(path) == name
        and (
            name
            in {
                "runtime.log",
                "task_history.jsonl",
                "operator_history.jsonl",
                "mastery_plans.jsonl",
                "mastery_routes.jsonl",
            }
            or (
                len(path.parts) >= 3
                and path.parts[0] == "windows"
                and path.name
                in {"runtime.log", "task_history.jsonl", "operator_history.jsonl"}
            )
        )
    )


def _scan_member(bundle, info, remaining, retained, position, focus_terms):
    coverage = {
        "member": info.filename,
        "member_bytes": info.file_size,
        "scan_byte_budget": remaining[0],
        "scan_line_budget": remaining[1],
        "scanned_bytes": 0,
        "scanned_lines": 0,
        "record_count": 0,
        "scan_complete": False,
        "stop_reason": None,
    }
    digest = hashlib.sha256()
    current = None
    history = info.filename.endswith(".jsonl")
    priority_counts = {}

    def finish():
        if current is None:
            return
        coverage["record_count"] += 1
        current["text"] = (
            current.pop("raw")
            .decode("utf-8", errors="replace")
            .encode("utf-8")[:MAX_RECORD_TEXT_BYTES]
            .decode("utf-8", errors="ignore")
        )
        if history and not current["text_truncated"]:
            try:
                entry = json.loads(current["text"])
                if isinstance(entry, dict):
                    stamp = entry.get("time", entry.get("current_time"))
                    if isinstance(stamp, (str, int, float)):
                        current["time"] = stamp
            except ValueError:
                current["parse_note"] = "invalid_json_line"
        current["text_sha256"] = _digest(current["text"].encode("utf-8"))
        current["raw_sha256"] = current.pop("digest").hexdigest()
        current["focus_matched"] = any(
            term in current["text"].casefold() for term in focus_terms
        )
        priority = _priority(current)
        current["_priority_order"] = priority_counts.get(priority, 0)
        priority_counts[priority] = current["_priority_order"] + 1
        current["_order"] = position[0]
        position[0] += 1
        # 同级按每个成员中的出现次数交错保留，再按附件顺序输出。
        if len(retained) < MAX_RECORDS:
            retained.append(current)
        elif _selection_key(current) < max(map(_selection_key, retained)):
            worst = max(range(len(retained)), key=lambda i: _selection_key(retained[i]))
            retained[worst] = current

    with bundle.open(info) as stream:
        line_start = True
        line_number = 0
        while remaining[0] > 0 and remaining[1] > 0:
            chunk = stream.readline(min(MAX_LINE_BYTES, remaining[0]))
            if not chunk:
                coverage["scan_complete"] = True
                break
            digest.update(chunk)
            remaining[0] -= len(chunk)
            coverage["scanned_bytes"] += len(chunk)
            if line_start:
                remaining[1] -= 1
                line_number += 1
                coverage["scanned_lines"] += 1
                match = _LOG_START.match(chunk.decode("utf-8", errors="replace"))
                if history or match or current is None:
                    finish()
                    current = {
                        "member": info.filename,
                        "kind": (
                            "current_snapshot"
                            if Path(info.filename).name.startswith("mastery_")
                            else "database_history"
                        )
                        if history
                        else "runtime_log",
                        "start_line": line_number,
                        "end_line": line_number,
                        "time": match[1] if match else None,
                        "level": match[2]
                        if match
                        else ("INFO" if history else "UNKNOWN"),
                        "raw": b"",
                        "digest": hashlib.sha256(),
                        "text_truncated": False,
                    }
            current["end_line"] = line_number
            current["digest"].update(chunk)
            available = MAX_RECORD_TEXT_BYTES - len(current["raw"])
            current["raw"] += chunk[:available]
            current["text_truncated"] |= len(chunk) > available
            line_start = chunk.endswith(b"\n")
        if coverage["scanned_bytes"] == info.file_size:
            coverage["scan_complete"] = True
        if not coverage["scan_complete"]:
            coverage["stop_reason"] = (
                "scan_byte_limit" if not remaining[0] else "scan_line_limit"
            )
            if current is not None:
                current["text_truncated"] = True
        finish()
    coverage["scanned_sha256"] = digest.hexdigest()
    return coverage


def _source_path(supplied):
    normalized = supplied.replace("\\", "/")
    if ".." in PurePosixPath(normalized).parts or "\0" in normalized:
        raise ValueError("不允许读取此文件")
    # 日志保留其他安装位置；只映射已有包名之后的路径，随后复用源码白名单。
    marker = "/arknights_mower/"
    if marker in normalized:
        normalized = "arknights_mower/" + normalized.rsplit(marker, 1)[1]
    elif re.match(r"^[A-Za-z]:/", normalized):
        raise ValueError("不允许读取此文件")
    return _allowed_source_path(normalized)


def _source_context(records):
    sources, omissions, seen = [], [], set()
    scanned = 0
    text_bytes = 0
    # 异常位置优先，最终日志记录仍按附件中的原始顺序输出。
    for record in sorted(records, key=_selection_key):
        if record["kind"] != "runtime_log":
            continue
        for match in _LOCATIONS.finditer(record["text"]):
            supplied, raw_line = (
                (match[1], match[2]) if match[1] else (match[3], match[4])
            )
            line = int(raw_line)
            if line < 1:
                omissions.append(
                    {"reason": "invalid_source_line", "record_id": record["id"]}
                )
                continue
            try:
                path = _source_path(supplied)
                key = (str(path), line)
                if key in seen:
                    continue
                seen.add(key)
                if len(sources) >= MAX_SOURCE_FILES:
                    omissions.append(
                        {"reason": "source_count_limit", "record_id": record["id"]}
                    )
                    continue
                remaining = MAX_SOURCE_SCAN_BYTES - scanned
                if path.stat().st_size > remaining:
                    omissions.append(
                        {"reason": "source_scan_byte_limit", "record_id": record["id"]}
                    )
                    continue
                with path.open("rb") as stream:
                    raw = stream.read(remaining + 1)
                scanned += len(raw)
                if len(raw) > remaining:
                    raise ValueError("源码超过读取上限")
                lines = raw.decode("utf-8").splitlines(keepends=True)
                if line > len(lines):
                    omissions.append(
                        {
                            "reason": "source_line_out_of_range",
                            "record_id": record["id"],
                        }
                    )
                    continue
                start, end = (
                    max(1, line - SOURCE_CONTEXT),
                    min(len(lines), line + SOURCE_CONTEXT),
                )
                text = "".join(lines[start - 1 : end])
                size = len(text.encode("utf-8"))
                if text_bytes + size > MAX_SOURCE_TEXT_BYTES:
                    omissions.append(
                        {"reason": "source_text_byte_limit", "record_id": record["id"]}
                    )
                    continue
                text_bytes += size
                # 仅显示安装目录内的可定位路径，不携带本机绝对路径。
                relative = path.relative_to(_PROJECT_ROOT).as_posix()
                source_hash = _digest(raw)
                sources.append(
                    {
                        "id": "source-"
                        + _identity(
                            relative, start, end, _digest(text.encode("utf-8"))
                        ),
                        "source_kind": "installed-current-source",
                        "historical_source_verified": False,
                        "file": relative,
                        "requested_line": line,
                        "start_line": start,
                        "end_line": end,
                        "source_sha256": source_hash,
                        "text_sha256": _digest(text.encode("utf-8")),
                        "text": text,
                        "record_id": record["id"],
                    }
                )
            except (OSError, ValueError, UnicodeError, RuntimeError):
                omissions.append(
                    {
                        "reason": "source_unavailable_or_disallowed",
                        "record_id": record["id"],
                    }
                )
    return (
        sources,
        omissions[:MAX_SOURCE_OMISSIONS],
        max(0, len(omissions) - MAX_SOURCE_OMISSIONS),
        scanned,
    )


def build_feedback_references(bundle_path: Path, focus_terms=None) -> dict:
    """读取最终反馈 ZIP 的日志成员；不提取文件、不执行源码或发送数据。"""
    if focus_terms is None:
        focus_terms = []
    if (
        not isinstance(focus_terms, list)
        or len(focus_terms) > 5
        or any(
            not isinstance(term, str) or not term.strip() or len(term) > 50
            for term in focus_terms
        )
    ):
        raise ValueError("关注词最多5个，每项须为1至50字")
    focus_terms = list(dict.fromkeys(term.strip().casefold() for term in focus_terms))
    if bundle_path.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError("反馈附件超过索引读取上限")
    retained, coverage = [], []
    remaining, position = [MAX_SCAN_BYTES, MAX_SCAN_LINES], [0]
    with ZipFile(bundle_path) as bundle:
        members = [
            info
            for info in bundle.infolist()
            if _reference_member(info.filename) and not info.is_dir()
        ]
        if len({info.filename for info in members}) != len(members):
            raise ValueError("反馈附件含重名日志，无法唯一定位引用")
        # 外层选定时段在先，其他时段维持 ZIP 成员顺序。
        members.sort(key=lambda info: info.filename != "runtime.log")
        admitted = members[:MAX_LOG_MEMBERS]
        for number, info in enumerate(admitted):
            # 先给每个后续成员预留同等份额，未用额度留给后续成员。
            left = len(admitted) - number
            allowance = [remaining[0] // left, remaining[1] // left]
            member_coverage = _scan_member(
                bundle, info, allowance, retained, position, focus_terms
            )
            remaining[0] -= member_coverage["scanned_bytes"]
            remaining[1] -= member_coverage["scanned_lines"]
            coverage.append(member_coverage)
    evidence_id = _identity(
        [
            (row["member"], row["member_bytes"], row["scanned_sha256"])
            for row in coverage
        ]
    )
    selected, text_bytes = [], 0
    for record in sorted(retained, key=_selection_key):
        size = len(record["text"].encode("utf-8"))
        if text_bytes + size <= MAX_TEXT_BYTES:
            text_bytes += size
            record["id"] = "log-" + _identity(
                record["member"],
                record["start_line"],
                record["end_line"],
                record["raw_sha256"],
            )
            selected.append(record)
    selected.sort(key=lambda row: row["_order"])
    sources, source_omissions, omitted_source_omissions, source_bytes = _source_context(
        selected
    )
    for row in selected:
        row.pop("_order")
        row.pop("_priority_order")
    index = {
        "schema_version": 1,
        "focus_terms": focus_terms,
        "evidence_id": evidence_id,
        "records": selected,
        "sources": sources,
        "coverage": {
            "members": coverage,
            "omitted_members": max(0, len(members) - MAX_LOG_MEMBERS),
            "indexed_record_count": len(selected),
            "unindexed_scanned_records": sum(row["record_count"] for row in coverage)
            - len(selected),
            "scan_complete": bool(coverage)
            and len(members) <= MAX_LOG_MEMBERS
            and all(row["scan_complete"] for row in coverage),
            "source_omissions": source_omissions,
            "omitted_source_omissions": omitted_source_omissions,
            "index_truncated": False,
            "source_scanned_bytes": source_bytes,
        },
        "limits": {
            "bundle_bytes": MAX_BUNDLE_BYTES,
            "scan_bytes": MAX_SCAN_BYTES,
            "scan_lines": MAX_SCAN_LINES,
            "scan_allocation": "remaining_budget_divided_by_remaining_members",
            "log_members": MAX_LOG_MEMBERS,
            "records": MAX_RECORDS,
            "record_text_bytes": MAX_RECORD_TEXT_BYTES,
            "text_bytes": MAX_TEXT_BYTES,
            "line_chunk_bytes": MAX_LINE_BYTES,
            "source_files": MAX_SOURCE_FILES,
            "source_scan_bytes": MAX_SOURCE_SCAN_BYTES,
            "source_text_bytes": MAX_SOURCE_TEXT_BYTES,
            "index_json_bytes": MAX_INDEX_BYTES,
            "index_escaped_json_bytes": MAX_ESCAPED_INDEX_BYTES,
        },
        "limitations": [
            "关注词仅机械匹配，不能证明因果；匹配记录优先，其次错误、警告、历史和业务日志。未索引不表示没有发生，扫描完成不证明历史完整。",
            "日志原文可能截断，原始成员和行号供复核；缺少证据时不能证明根因。",
            "源码来自当前安装，不证明它与故障发生时的版本一致。",
            ANALYSIS_NOTE,
        ],
    }
    # 同时限制通常 JSON 与 ASCII 转义 JSON，调用方无需盲切有效引用。
    while (
        len(json.dumps(index, ensure_ascii=False).encode("utf-8")) > MAX_INDEX_BYTES
        or len(json.dumps(index).encode("utf-8")) > MAX_ESCAPED_INDEX_BYTES
    ):
        index["coverage"]["index_truncated"] = True
        if selected:
            worst = max(range(len(selected)), key=lambda i: (_priority(selected[i]), i))
            removed = selected.pop(worst)
            sources[:] = [
                source for source in sources if source["record_id"] != removed["id"]
            ]
            index["coverage"]["indexed_record_count"] -= 1
            index["coverage"]["unindexed_scanned_records"] += 1
        elif sources:
            sources.pop()
        else:
            raise ValueError("反馈索引元数据超过读取上限")
    return index


def validate_feedback_analysis(analysis: dict, index: dict) -> dict:
    """验证逐项引用存在；不验证模型文字与证据之间的语义关系。"""
    if not isinstance(analysis, dict) or analysis.get("status") not in (
        "analyzed",
        "unknown",
    ):
        raise ValueError("分析状态无效")
    claims, unknowns = analysis.get("claims"), analysis.get("unknowns")
    if (
        not isinstance(claims, list)
        or len(claims) > 8
        or not isinstance(unknowns, list)
        or len(unknowns) > 8
    ):
        raise ValueError("分析条目数量无效")
    if any(
        not isinstance(item, str) or not item.strip() or len(item) > 1000
        for item in unknowns
    ):
        raise ValueError("未知事项无效")
    if analysis["status"] == "analyzed" and not claims:
        raise ValueError("分析缺少带引用的条目")
    if analysis["status"] == "unknown" and not unknowns:
        raise ValueError("未知状态须说明证据不足之处")
    logs = {row["id"] for row in index["records"]}
    sources = {row["id"] for row in index["sources"]}
    source_records = {row["id"]: row.get("record_id") for row in index["sources"]}
    validated = []
    for claim in claims:
        if not isinstance(claim, dict) or claim.get("kind") not in (
            "log_interpretation",
            "code_inference",
        ):
            raise ValueError("分析条目类型无效")
        text, refs = claim.get("text"), claim.get("references")
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise ValueError("分析条目文字无效")
        if (
            not isinstance(refs, list)
            or not 1 <= len(refs) <= 8
            or any(
                not isinstance(ref, str) or ref not in logs | sources for ref in refs
            )
        ):
            raise ValueError("分析引用不属于此次反馈附件")
        if not logs.intersection(refs) or (
            claim["kind"] == "code_inference" and not sources.intersection(refs)
        ):
            raise ValueError("分析条目缺少所需日志或源码引用")
        if claim["kind"] == "code_inference" and any(
            source_records[source_id] not in refs
            for source_id in sources.intersection(refs)
        ):
            raise ValueError("源码关联记录须由同一分析条目引用")
        validated.append(
            {
                "kind": claim["kind"],
                "text": text,
                "references": list(dict.fromkeys(refs)),
            }
        )
    return {
        "status": analysis["status"],
        "claims": validated,
        "unknowns": list(unknowns),
        "note": ANALYSIS_NOTE,
    }
