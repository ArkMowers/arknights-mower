from datetime import datetime

from arknights_mower.utils.email import Email
from arknights_mower.utils.log import get_log_by_time, logger


def submit_issue(
    description: str,
    issue_type: str = "Bug",
    start_time: str = None,
    end_time: str = None,
):
    """
    上报用户未解决的问题给开发组，可附带日志
    """
    try:
        log_files = []
        logger.debug(
            f"Submitting issue: {description}, type: {issue_type}, start_time: {start_time}, end_time: {end_time}"
        )
        if issue_type == "Bug":
            if not (start_time and end_time):
                return "请提供问题发生的起止时间（start_time 和 end_time，本地时间 YYYY-MM-DD HH:MM:SS），以便附加日志。"
            # 按软件本地时间解析。
            st = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            et = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
            print(
                f"Submitting issue: {description}, type: {issue_type}, start_time: {st}, end_time: {et}"
            )
            log_files = get_log_by_time(et)
            if not log_files:
                return "未找到对应时间的日志文件，无法上报。"
            body = f"<p>Bug 发生时间区间:{st}--{et}</p><br><p>{description}</p>"
        else:
            body = description
        email = Email(
            body,
            "Mower " + issue_type,
            None,
            attach_files=None if issue_type != "Bug" else log_files,
        )
        email.send(["354013233@qq.com", "1273725854@qq.com"])
        return "邮件发送成功！"
    except Exception as e:
        print(e)
        return f"反馈发送失败，请确保邮箱功能正常使用\n{e}"


submit_issue_tool_def = {
    "type": "function",
    "function": {
        "name": "submit_issue",
        "description": (
            "通过已配置的邮箱向开发组发送问题描述，Bug 反馈附带日志。"
            "仅在用户明确要求发送反馈时调用，单纯排查或整理描述不发送。"
            "描述包含实际问题和期望行为，不补造用户未提供的事实。"
            "Bug 必须有本地起止时间，格式 YYYY-MM-DD HH:MM:SS，不是 Unix 时间戳或毫秒值。"
            "调用前核对结束时间晚于开始时间，间隔不超过15分钟；范围过长时请用户缩小。"
            "只有一个时间点时可建议后续10分钟作为范围，确认后发送；自然语言时间有歧义时确认具体日期和时区。"
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
