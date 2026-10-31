from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory

from arknights_mower.agent.tools.issue_evidence import (
    MAX_MAIL_BYTES,
    collect_evidence,
    parse_interval,
)
from arknights_mower.utils.email import Email
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path


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
                count = len(attachments) - 2
                body = (
                    f"<p>Bug 发生时间区间:{start}--{end}</p><p>{body}</p>"
                    f"<p>附带 {count} 张关键截图，筛选依据及省略说明见 evidence.json。"
                    "完整记录可从日志调度导出。</p>"
                )
            email = Email(body, "Mower " + issue_type, None, attach_files=attachments)
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
