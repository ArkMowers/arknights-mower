import json
import os
import platform
from datetime import datetime
from email.utils import format_datetime
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory

from arknights_mower import __version__
from arknights_mower.agent.tools.issue_evidence import (
    MAX_MAIL_BYTES,
    collect_evidence,
    parse_interval,
)
from arknights_mower.utils import config
from arknights_mower.utils.config.plan_advanced import export_advanced_settings
from arknights_mower.utils.email import Email
from arknights_mower.utils.git_rev import revision_info
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path

MAX_PLAN_BYTES = 256 * 1024


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
    context["plan"] = {"file": "plan.json", "bytes": len(data)}
    if len(data) <= MAX_PLAN_BYTES:
        path = output / "plan.json"
        path.write_bytes(data)
        attachments.append(path)
        context["plan"]["status"] = "attached"
    else:
        context["plan"].update(
            status="omitted", reason="排班 JSON 超过256 KiB，未附加。"
        )
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
                plan_note = context["plan"].get(
                    "reason", "附带当前保存的排班 plan.json。"
                )
                body = (
                    f"<p>所选问题时间区间：{escape(interval['start'])} 至 "
                    f"{escape(interval['end'])}</p><p>{body}</p>"
                    f"<p>{coverage}</p><p>附带 {count} 张关键截图，"
                    "截图按时间关联，未判断画面内容；筛选依据及省略说明见 evidence.json。</p>"
                    f"<p>{plan_note}{context['configuration_note']}"
                    "版本、平台与时区信息见 context.json。</p>"
                )
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
            "描述包含实际问题和期望行为，不补造用户未提供的事实。"
            "Bug 必须有本地起止时间，格式 YYYY-MM-DD HH:MM:SS，不是 Unix 时间戳或毫秒值。"
            "调用前核对结束时间晚于开始时间，间隔不超过15分钟；范围过长时请用户缩小。"
            "只有一个时间点时可建议后续10分钟作为范围，确认后发送；自然语言时间有歧义时确认具体日期和时区。"
            "已从日志或用户描述确定关键时刻时，用 screenshot_times 指定至多4个本地时间；不得编造时间。"
            "不传时按不同错误、警告首次有可用截图的时间自动筛选；传空列表表示不附截图。"
            "截图来自日志调度，按时间关联而非画面内容判断；重复或超过单张512 KiB的截图会省略，总计不超过2 MiB。"
            "Bug 自动附带版本、平台、Python与带UTC偏移的时间信息，以及当前保存的主副排班和白名单高级设置；"
            "配置属于反馈生成时刻，不是故障发生时的历史快照。排班JSON超过256 KiB时省略并说明。"
            "正文披露所选区间、压缩日志实际记录首尾及截断情况，实际记录不保证连续覆盖所有时刻。"
            "邮件编码后上限8 MiB；没有相关截图仍可附日志发送，按实际结果说明。"
            "功能建议不要求时间范围。按工具实际返回说明成功或失败，不把缺日志或发送失败说成已上报。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "用户要求发送的问题或功能建议，包含实际现象与期望行为。",
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
