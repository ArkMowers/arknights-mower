import json
import os
import platform
import re
import shutil
import unicodedata
from datetime import datetime
from email.utils import format_datetime
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from arknights_mower import __version__
from arknights_mower.agent.tools.feedback_records import collect_feedback_records
from arknights_mower.agent.tools.issue_evidence import (
    MAX_LOG_UNCOMPRESSED_BYTES,
    MAX_MAIL_BYTES,
    collect_evidence,
    parse_interval,
)
from arknights_mower.utils import config
from arknights_mower.utils.config.plan_advanced import export_advanced_settings
from arknights_mower.utils.diagnostics import (
    LOG_FILENAME,
    README_FILENAME,
    SCREENSHOT_DIRECTORY,
)
from arknights_mower.utils.email import Email
from arknights_mower.utils.git_rev import revision_info
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path


def _feedback_archive_name(start, description):
    """沿用日志调度的时间格式，用首个问题行补充可辨认的文件名。"""
    lines = [line.strip() for line in description.splitlines() if line.strip()]
    line = next(
        (
            line
            for line in lines
            if not re.match(
                r"^(?:版本|Mower\s*版本|平台|时间|Bug\s*发生时间区间|version|platform)\s*[:：]",
                line,
                re.IGNORECASE,
            )
        ),
        "问题反馈",
    )
    line = "".join(
        " " if unicodedata.category(char).startswith("C") else char for char in line
    )
    summary = " ".join(re.sub(r'[<>:"/\\|?*]', " ", line).split())
    summary = summary[:40].strip(" .") or "问题反馈"
    return f"feedback-{start:%Y%m%d-%H%M%S}-{summary}.zip"


def _package_evidence(attachments, output, start, end, description):
    """按日志调度导出布局打包，区间日志直接展开到同一压缩包内。"""
    destination = output / _feedback_archive_name(start, description)
    files = {Path(path).name: Path(path) for path in attachments}
    manifest = files.get("evidence.json")
    evidence = json.loads(manifest.read_text(encoding="utf-8")) if manifest else {}
    screenshots = {row["file"]: row for row in evidence.get("screenshots", [])}
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as bundle:
        for name, path in files.items():
            if name == "evidence.json":
                continue
            if name == "runtime.zip":
                with ZipFile(path) as logs:
                    info = logs.getinfo("runtime.txt")
                    if info.file_size > MAX_LOG_UNCOMPRESSED_BYTES:
                        raise ValueError("区间日志超过解压大小上限，尚未发送。")
                    with (
                        logs.open(info) as source,
                        bundle.open(LOG_FILENAME, "w") as target,
                    ):
                        shutil.copyfileobj(source, target, length=64 * 1024)
                info = bundle.getinfo(LOG_FILENAME)
                evidence.setdefault("log_archive", {}).update(
                    file=LOG_FILENAME,
                    bytes=info.compress_size,
                    uncompressed_bytes=info.file_size,
                )
            elif name == "runtime.txt":
                bundle.write(path, "runtime.txt")
                evidence.setdefault("excerpt", {})["file"] = "runtime.txt"
            elif path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                row = screenshots.get(name)
                relative = row["source"] if row else name
                arcname = f"{SCREENSHOT_DIRECTORY}/{relative}"
                bundle.write(path, arcname, compress_type=ZIP_STORED)
                if row is not None:
                    row["file"] = arcname
            else:
                bundle.write(path, name)
        if manifest:
            bundle.writestr(
                "evidence.json", json.dumps(evidence, ensure_ascii=False, indent=2)
            )
        archive = evidence.get("log_archive", {})
        count = sum(
            path.suffix.lower() in {".jpg", ".jpeg", ".png"} for path in files.values()
        )
        bundle.writestr(
            README_FILENAME,
            f"日志调度导出\n问题：{description}\n"
            f"时间范围：{start:%Y-%m-%d %H:%M:%S} 至 {end:%Y-%m-%d %H:%M:%S}\n"
            f"日志：{archive.get('record_count', 0)} 条\n截图：{count} 张\n"
            f"包含截图：{'是' if count else '否'}\n"
            "排班表为导出时当前保存的配置，不代表日志发生时的排班。\n"
            "任务及干员历史按所选区间只读导出，结果与不可用原因见 evidence.json。\n"
            "日志及截图的实际范围与省略原因见 evidence.json；日志摘要不代替区间日志。\n",
        )
    return destination


def _feedback_context(start, end, output):
    generated = datetime.now().astimezone()
    context = {
        "mower_version": __version__,
        "revision": revision_info(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "android": os.environ.get("MOWER_ANDROID") == "1",
        },
        "generated_at": generated.isoformat(timespec="seconds"),
        "requested_interval": {
            "start": start.astimezone().isoformat(timespec="seconds"),
            "end": end.astimezone().isoformat(timespec="seconds"),
        },
        "settings": {"right_side_room_order": config.conf.right_side_room_order},
        "configuration_note": "排班及设置为反馈生成时当前保存的配置，不是问题发生时的历史快照。",
    }
    plan = config.plan.model_dump(exclude_none=True)
    plan["advanced_settings"] = export_advanced_settings(config.conf)
    data = json.dumps(plan, ensure_ascii=False, indent=2).encode("utf-8")
    attachments = []
    context["plan"] = {"file": "plan.json", "bytes": len(data), "status": "attached"}
    path = output / "plan.json"
    path.write_bytes(data)
    attachments.append(path)
    path = output / "context.json"
    path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    return [path, *attachments], context, generated


def _log_coverage(attachments):
    manifest = next(
        (Path(path) for path in attachments if Path(path).name == "evidence.json"),
        None,
    )
    try:
        evidence = json.loads(manifest.read_text(encoding="utf-8")) if manifest else {}
    except (OSError, ValueError):
        evidence = {}
    archive = evidence.get("log_archive") or {}
    if not archive:
        return "未提供压缩日志的实际覆盖信息，请查看 evidence.json 和已附日志。"
    first, last = archive.get("first_time"), archive.get("last_time")
    if not archive.get("file"):
        summary = "压缩日志未附加，无法提供其实际覆盖范围；请查看已附文字摘要。"
    elif first and last:
        summary = (
            f"压缩日志中实际记录首尾：{escape(str(first))} 至 {escape(str(last))}，"
            f"共 {escape(str(archive.get('record_count', 0)))} 条。"
        )
    else:
        summary = "压缩日志中没有可附加的记录。"
    if archive.get("truncated"):
        summary += "日志达到附件字节上限，部分内容已省略。"
    if not archive.get("scan_complete", True):
        summary += "日志来源未全部读取，原因及省略说明见 evidence.json。"
    if archive.get("unreadable_files"):
        summary += "部分日志文件读取失败。"
    if archive.get("archive_source_limited"):
        summary += "包含异常归档中的日志片段，归档来源本身可能已有截断。"
    return summary + "实际记录不代表整个区间内每个时刻都有日志。"


def _database_coverage(metadata):
    sections = []
    for table, label in (("log", "任务历史"), ("agent_action", "干员历史")):
        result = metadata.get("tables", {}).get(table, {})
        if result.get("status") in {"exported", "empty", "partial"}:
            section = f"{label}：{result.get('row_count', 0)} 条"
        else:
            section = f"{label}不可用"
        if result.get("truncated"):
            section += "，导出不完整"
        if result.get("missing_columns"):
            section += "，部分旧版字段不存在"
        sections.append(section)
    return "；".join(sections) + "。实际范围、缺失和读取失败原因见 evidence.json。"


def submit_issue(
    description: str,
    issue_type: str = "Bug",
    start_time: str = None,
    end_time: str = None,
    screenshot_times: list[str] = None,
):
    """
    上报用户未解决的问题给开发组，附带时间范围内的日志和关键截图
    """
    try:
        with TemporaryDirectory(prefix="mower-feedback-") as temporary:
            attachments = None
            body = escape(description)
            if issue_type == "Bug":
                if not (start_time and end_time):
                    return "请提供问题发生的起止时间（本地时间 YYYY-MM-DD HH:MM:SS），以便附加日志和关键截图。"
                start, end = parse_interval(start_time, end_time)
                attachments = collect_evidence(
                    Path(get_path("@app/log")),
                    Path(get_path("@app/screenshot")),
                    start,
                    end,
                    Path(temporary),
                    screenshot_times,
                )
                record_files, record_info = collect_feedback_records(
                    Path(get_path("@app/tmp/data.db")), start, end, Path(temporary)
                )
                manifest = Path(temporary) / "evidence.json"
                evidence = (
                    json.loads(manifest.read_text(encoding="utf-8"))
                    if manifest.is_file()
                    else {}
                )
                evidence["database_records"] = record_info
                manifest.write_text(
                    json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                if manifest not in [Path(path) for path in attachments]:
                    attachments.append(manifest)
                attachments.extend(record_files)
                count = sum(
                    Path(path).suffix.lower() in {".jpg", ".jpeg", ".png"}
                    for path in attachments
                )
                coverage = _log_coverage(attachments)
                context_files, context, generated = _feedback_context(
                    start, end, Path(temporary)
                )
                attachments = [*attachments, *context_files]
                interval = context["requested_interval"]
                filename = _feedback_archive_name(start, description)
                body = (
                    f"<p>所选问题时间区间：{escape(interval['start'])} 至 "
                    f"{escape(interval['end'])}</p><p>{body}</p>"
                    f"<p>诊断附件：{escape(filename)}。解压后直接查看 runtime.log、screenshots 目录和排班表。</p>"
                    f"<p>{coverage}</p><p>附带 {count} 张关键截图，"
                    "截图按时间关联，未判断画面内容；筛选依据及省略说明见 evidence.json。</p>"
                    f"<p>包内附带当前排班 plan.json。{context['configuration_note']}"
                    "版本、平台与时区信息见 context.json。</p>"
                    f"<p>{_database_coverage(record_info)}</p>"
                )
                attachments = [
                    _package_evidence(
                        attachments, Path(temporary), start, end, description
                    )
                ]
            email = Email(body, "Mower " + issue_type, None, attach_files=attachments)
            if issue_type == "Bug":
                email.msg["Date"] = format_datetime(generated)
            if len(email.msg.as_bytes()) > MAX_MAIL_BYTES:
                return (
                    "反馈邮件超过8 MiB，尚未发送。请缩小问题时间范围或精简描述后重试。"
                )
            email.send(["354013233@qq.com", "1273725854@qq.com"])
        return "邮件发送成功！"
    except ValueError as exc:
        return str(exc)
    except Exception as e:
        logger.exception("反馈发送失败")
        return f"反馈发送失败，请确保邮箱功能正常使用\n{e}"


submit_issue_tool_def = {
    "type": "function",
    "function": {
        "name": "submit_issue",
        "description": (
            "通过已配置的邮箱向开发组发送问题描述，Bug 反馈附带该时间范围内的日志和至多4张关键截图。"
            "仅在用户明确要求发送反馈时调用，单纯排查或整理描述不发送。"
            "完整保留用户报告的现象，描述按用户观察、期望行为、复现条件、已查证据及时间、AI推断、未确认事项分段。"
            "缺失内容注明未知，不补造事实，也不因缺少可选信息反复要求确认。"
            "任务名称、队列快照或计划创建不代表实际执行完成；缺少后续记录不代表没有执行。"
            "Bug 必须有本地起止时间，格式 YYYY-MM-DD HH:MM:SS，不是 Unix 时间戳或毫秒值。"
            "调用前核对结束时间晚于开始时间，间隔不超过15分钟；范围过长时请用户缩小。"
            "只有一个时间点时可建议后续10分钟作为范围，确认后发送；自然语言时间有歧义时确认具体日期和时区。"
            "已从日志或用户描述确定关键时刻时，用 screenshot_times 指定至多4个本地时间；不得编造时间。"
            "不传时按不同错误、警告首次有可用截图的时间自动筛选；传空列表表示不附截图。"
            "截图来自日志调度，按时间关联而非画面内容判断；重复或超过单张512 KiB的截图会省略，总计不超过2 MiB。"
            "Bug 自动附带版本、平台、Python与带UTC偏移的时间信息，以及当前保存的主副排班和白名单高级设置；"
            "配置属于反馈生成时刻，不是故障发生时的历史快照；成功发送时必须包含当前排班表。"
            "正文披露所选区间、压缩日志实际记录首尾及截断情况，实际记录不保证连续覆盖所有时刻。"
            "自动只读导出区间内任务日志与干员历史，保留任务、心情、位置和关联字段，读取限制与缺失写入清单；不导出全库。"
            "附件按 feedback-时间-问题简述.zip 命名，采用日志调度导出的 runtime.log、screenshots、plan.json 和 readme.txt 布局，不嵌套日志ZIP。"
            "邮件编码后上限8 MiB；没有相关截图仍可附日志发送，按实际结果说明。"
            "功能建议不要求时间范围。按工具实际返回说明成功或失败，不把缺日志或发送失败说成已上报。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "用户要求发送的问题或功能建议。Bug需保留用户观察及期望，分列复现条件、已查证据及时间、AI推断和未确认事项，未知项如实说明。",
                    "default": "",
                },
                "issue_type": {
                    "type": "string",
                    "description": "Bug 表示附日志的问题反馈；Feature 表示功能建议。",
                    "enum": ["Bug", "Feature"],
                    "default": "Bug",
                },
                "start_time": {
                    "type": "string",
                    "description": (
                        "Using the user's local time zone (not UTC). "
                        "Format: 'YYYY-MM-DD HH:MM:SS', e.g. '2025-06-29 14:35:00'. "
                        "Do not pass a Unix timestamp or fractional seconds."
                    ),
                },
                "screenshot_times": {
                    "type": "array",
                    "maxItems": 4,
                    "items": {"type": "string"},
                    "description": "分析发现的关键问题时刻，本地 YYYY-MM-DD HH:MM:SS，须在反馈范围内。每个时刻选取同秒或此前30秒内的最近截图。省略则自动筛选错误和警告；空列表不附截图。",
                },
                "end_time": {
                    "type": "string",
                    "description": (
                        "Using the user's local time zone (not UTC). "
                        "Format: 'YYYY-MM-DD HH:MM:SS', e.g. '2025-06-29 14:45:00'. "
                        "Must be later than start_time and at most 15 minutes after it. "
                        "Do not pass a Unix timestamp or fractional seconds."
                    ),
                },
            },
            "required": ["description"],
        },
    },
}
